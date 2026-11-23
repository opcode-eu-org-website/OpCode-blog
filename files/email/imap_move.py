#!/usr/bin/env python3

# SPDX-FileCopyrightText: Robert Ryszard Paciorek <rrp@opcode.eu.org>
# SPDX-License-Identifier: MIT

# created by Gemini AI, 2026


# ==============================================================================
# IMPORTY
# ==============================================================================

import sys
import os
import ssl
import imaplib
import email
import mailbox
import base64
import json
from email.header import decode_header

# ==============================================================================
# FUNKCJA POMOCNICZA DO ODŚWIEŻANIA TOKENÓW OAUTH2
# ==============================================================================

def get_gmail_access_token(client_id, client_secret, refresh_token):
	import urllib.request
	import urllib.parse
	"""Pobiera nowy Access Token z Google serwera tokenów."""
	url = "https://oauth2.googleapis.com/token"
	params = {
		"client_id": client_id,
		"client_secret": client_secret,
		"refresh_token": refresh_token,
		"grant_type": "refresh_token"
	}
	data = urllib.parse.urlencode(params).encode("utf-8")
	req = urllib.request.Request(url, data=data, method="POST")
	
	with urllib.request.urlopen(req) as response:
		res_data = json.loads(response.read().decode("utf-8"))
		return res_data["access_token"]

# ==============================================================================
# KONFIGURACJA I OBSŁUGA PLIKU JSON
# ==============================================================================

CONFIG_TEMPLATE = """{
  "SRC_HOST": "imap.gmail.com",
  "SRC_PORT": 993,
  "SRC_USER": "user@gmail.com",
  "SRC_AUTH_TYPE": "PLAIN",
  "SRC_PASSWORD_OR_TOKEN": "abcdefghijklmnop",
  "SRC_CLIENT_ID": "",
  "SRC_CLIENT_SECRET": "",
  "SRC_REFRESH_TOKEN": "",
  "SRC_FOLDER": "INBOX",
  "SRC_TRASH_FOLDER": "[Gmail]/Kosz",
  
  "DST_MODE": "MAILDIR",
  "DST_LOCAL_MAILDIR_PATH": "./maildir_backup",
  "DST_HOST": "mail.example.com",
  "DST_PORT": 993,
  "DST_USER": "user@example.com",
  "DST_AUTH_TYPE": "PLAIN",
  "DST_PASSWORD_OR_TOKEN": "MojeTajneHaslo123",
  "DST_CLIENT_ID": "",
  "DST_CLIENT_SECRET": "",
  "DST_REFRESH_TOKEN": "",
  "DST_FOLDER": "INBOX"
}
/*
Opis opcji konfiguracyjnych:
- SRC_HOST: Adres serwera źródłowego IMAP.
- SRC_PORT: Port serwera źródłowego (zazwyczaj 993 dla SSL).
- SRC_USER: Nazwa użytkownika / adres e-mail na serwerze źródłowym.
- SRC_AUTH_TYPE: Typ autoryzacji dla źródła: "PLAIN" lub "OAUTH2".
- SRC_PASSWORD_OR_TOKEN: Hasło, wygenerowane (https://myaccount.google.com/apppasswords) hasło aplikacji lub token dostępowy. Puste aby uzyskiwać token OAUTH2 w oparciu o SRC_CLIENT_ID, SRC_CLIENT_SECRET i SRC_REFRESH_TOKEN.
- SRC_CLIENT_ID: Client ID dla OAuth2 (opcjonalnie).
- SRC_CLIENT_SECRET: Client Secret dla OAuth2 (opcjonalnie).
- SRC_REFRESH_TOKEN: Refresh Token dla OAuth2 (opcjonalnie).
- SRC_FOLDER: Folder źródłowy do przenoszenia wiadomości (np. "INBOX").
- SRC_TRASH_FOLDER: Folder kosza na serwerze źródłowym.
- DST_MODE: Tryb działania - "IMAP" (przenoszenie na inny serwer) lub "MAILDIR" (zapis lokalny).
- DST_LOCAL_MAILDIR_PATH: Ścieżka do lokalnego katalogu Maildir (dla trybu MAILDIR).
- DST_HOST, DST_PORT, DST_USER, DST_AUTH_TYPE, DST_PASSWORD_OR_TOKEN, DST_CLIENT_ID, DST_CLIENT_SECRET, DST_REFRESH_TOKEN, DST_FOLDER: Ustawienia serwera docelowego (dla trybu IMAP), analogiczne jak SRC_*.
*/
"""

def load_config():
	config_path = os.path.expanduser("~/.imap_move.json")
	if len(sys.argv) > 1:
		config_path = sys.argv[1]

	if not os.path.exists(config_path):
		print(f"[-] Błąd: Nie znaleziono pliku konfiguracyjnego: {config_path}", file=sys.stderr)
		print("[-] Utwórz plik konfiguracyjny na wzór poniższego przykładu:\n", file=sys.stderr)
		print(CONFIG_TEMPLATE, file=sys.stderr)
		sys.exit(1)
	
	try:
		with open(config_path, "r", encoding="utf-8") as f:
			# Proste wczytanie JSON (uwaga: komentarze w szablonie powyżej mają charakter informacyjny, 
			# standardowy json.load może wymagać czystego JSON-a)
			content = f.read()
			config_data = json.loads(content)
	except Exception as e:
		print(f"[-] Błąd podczas parsowania pliku konfiguracyjnego {config_path}: {e}", file=sys.stderr)
		sys.exit(1)
	
	# Obsługa OAUTH2 dla źródła, jeżeli SRC_PASSWORD_OR_TOKEN nie jest ustawiony
	if config_data.get("SRC_AUTH_TYPE", "").upper() == "OAUTH2" and not config_data.get("SRC_PASSWORD_OR_TOKEN"):
		config_data["SRC_PASSWORD_OR_TOKEN"] = get_gmail_access_token(
			config_data.get("SRC_CLIENT_ID"),
			config_data.get("SRC_CLIENT_SECRET"),
			config_data.get("SRC_REFRESH_TOKEN")
		)

	# Obsługa OAUTH2 dla celu, jeżeli DST_PASSWORD_OR_TOKEN nie jest ustawiony
	if config_data.get("DST_AUTH_TYPE", "").upper() == "OAUTH2" and not config_data.get("DST_PASSWORD_OR_TOKEN"):
		config_data["DST_PASSWORD_OR_TOKEN"] = get_gmail_access_token(
			config_data.get("DST_CLIENT_ID"),
			config_data.get("DST_CLIENT_SECRET"),
			config_data.get("DST_REFRESH_TOKEN")
		)

	return config_data

CONFIG = load_config()

# ==============================================================================
# POZOSTAŁE FUNKCJE POMOCNICZE
# ==============================================================================

def decode_mime_header(header_val):
	"""Przekształca zakodowane nagłówki wiadomości (np. UTF-8) na czytelny tekst."""
	if not header_val:
		return "(Brak)"
	decoded_parts = decode_header(header_val)
	header_text = ""
	for part, encoding in decoded_parts:
		if isinstance(part, bytes):
			header_text += part.decode(encoding or "utf-8", errors="replace")
		else:
			header_text += str(part)
	return header_text

def authenticate_imap(client, username, auth_type, password_or_token):
	"""Logowanie do serwera IMAP przy użyciu PLAIN lub XOAUTH2."""
	if auth_type.upper() == "OAUTH2":
		# Format komendy XOAUTH2: user={user}\x01auth=Bearer {token}\x01\x01
		auth_string = f"user={username}\xa0auth=Bearer {password_or_token}\xa0"
		auth_bytes = auth_string.replace('\xa0', '\x01').encode('utf-8')
		
		# Inicjalizacja mechanizmu authenticate w imaplib
		res, data = client.authenticate('XOAUTH2', lambda x: auth_bytes)
		if res != 'OK':
			raise Exception(f"Błąd uwierzytelnienia OAuth2 dla {username}: {data}")
	else:
		# Standardowe logowanie login/hasło
		res, data = client.login(username, password_or_token)
		if res != 'OK':
			raise Exception(f"Błąd logowania dla {username}: {data}")

def connect_imap(host, port, username, auth_type, password_or_token):
	"""Nawiązuje szyfrowane połączenie SSL/TLS z serwerem IMAP."""
	context = ssl.create_default_context()
	client = imaplib.IMAP4_SSL(host, port, ssl_context=context)
	authenticate_imap(client, username, auth_type, password_or_token)
	return client

def save_to_maildir(maildir_path, raw_msg):
	"""Zapisuje wiadomość do lokalnego Maildira."""
	mbox = mailbox.Maildir(maildir_path, create=True)
	mbox.add(raw_msg)


# ==============================================================================
# GŁÓWNA LOGIKA
# ==============================================================================

def main():
	print(f"[+] Łączenie z serwerem źródłowym: {CONFIG['SRC_HOST']}...")
	src_client = connect_imap(CONFIG['SRC_HOST'], CONFIG['SRC_PORT'], CONFIG['SRC_USER'], CONFIG['SRC_AUTH_TYPE'], CONFIG['SRC_PASSWORD_OR_TOKEN'])
	
	dst_client = None
	if CONFIG['DST_MODE'].upper() == "IMAP":
		print(f"[+] Łączenie z serwerem docelowym: {CONFIG['DST_HOST']}...")
		dst_client = connect_imap(CONFIG['DST_HOST'], CONFIG['DST_PORT'], CONFIG['DST_USER'], CONFIG['DST_AUTH_TYPE'], CONFIG['DST_PASSWORD_OR_TOKEN'])
	
	# Wybór folderu źródłowego
	res, _ = src_client.select(CONFIG['SRC_FOLDER'])
	if res != 'OK':
		print(f"[-] Błąd: Nie można otworzyć folderu źródłowego {CONFIG['SRC_FOLDER']}", file=sys.stderr)
		sys.exit(1)
	
	# Pobranie listy UID wszystkich wiadomości
	res, data = src_client.uid('search', None, 'ALL')
	if res != 'OK':
		print("[-] Błąd podczas wyszukiwania wiadomości.", file=sys.stderr)
		sys.exit(1)
	
	message_uids = data[0].split()
	total_msgs = len(message_uids)
	print(f"[+] Znaleziono wiadomości do przetworzenia: {total_msgs}")
	
	for idx, uid in enumerate(message_uids, 1):
		# 1. Pobierz wiadomość
		res, msg_data = src_client.uid('fetch', uid, '(RFC822)')
		if res != 'OK' or not msg_data or not msg_data[0]:
			print(f"[-] BŁĄD: Nie udało się pobrać wiadomości UID: {uid.decode()}", file=sys.stderr)
			sys.exit(1)
		
		raw_message = msg_data[0][1]
		
		# Parsowanie nagłówków do wypisania na stdout
		parsed_email = email.message_from_bytes(raw_message)
		subject = decode_mime_header(parsed_email.get("Subject"))
		sender = decode_mime_header(parsed_email.get("From"))
		
		# 2. Zapisz wiadomość na serwer wyjściowy / do Maildir
		try:
			if CONFIG['DST_MODE'].upper() == "IMAP":
				# Zapis (APPEND) na docelowy serwer IMAP
				res_app, _ = dst_client.append(CONFIG['DST_FOLDER'], None, None, raw_message)
				if res_app != 'OK':
					raise Exception("Serwer docelowy odrzucił komendę APPEND")
			elif CONFIG['DST_MODE'].upper() == "MAILDIR":
				# Zapis do lokalnego Maildir
				save_to_maildir(CONFIG['DST_LOCAL_MAILDIR_PATH'], raw_message)
			else:
				raise Exception(f"Nieznany tryb: {CONFIG['DST_MODE']}")
		except Exception as e:
			# 3. Przerwij w przypadku błędu (nie zapisania wiadomości)
			print(f"\n[-] BŁĄD KRYTYCZNY podczas zapisywania wiadomości UID {uid.decode()}: {e}", file=sys.stderr)
			print("[-] Przetwarzanie zostało przerwane, wiadomość NIE została usunięta ze źródła.", file=sys.stderr)
			sys.exit(1)
		
		# 4. Wypisz na stdout temat i nadawcę skopiowanej wiadomości
		print(f"[{idx}/{total_msgs}] Skopiowano: Od: {sender} | Temat: {subject}")
		
		# 5. Przenieś wiadomość do kosza na serwerze wejściowym
		# Najbardziej kompatybilna metoda przeniesienia do Kosza na IMAP to MOVE (lub COPY + flag \Deleted)
		res_move, _ = src_client.uid('MOVE', uid, CONFIG['SRC_TRASH_FOLDER'])
		if res_move != 'OK':
			# Fallback dla serwerów bez obsługi rozszerzenia MOVE (COPY do Trash + oznacz jako Deleted)
			src_client.uid('COPY', uid, CONFIG['SRC_TRASH_FOLDER'])
			src_client.uid('STORE', uid, '+FLAGS', '(\\Deleted)')
			src_client.expunge()

	print("[+] Zakończono pomyślnie. Wszystkie wiadomości zostały przeniesione.")
	
	# Zamknięcie połączeń
	src_client.logout()
	if dst_client:
		dst_client.logout()

if __name__ == "__main__":
	main()
