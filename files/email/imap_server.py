#!/usr/bin/env python3

# SPDX-FileCopyrightText: Robert Ryszard Paciorek <rrp@opcode.eu.org>
# SPDX-License-Identifier: MIT

# created by Gemini AI, 2026

import argparse
import mailbox
import os
import re
import socket
import socketserver
import sys


def parse_imap_args(args_str):
	tokens = []
	pattern = r'"([^"\\]*(?:\\.[^"\\]*)*)"|(\S+)'
	for m in re.finditer(pattern, args_str):
		q, u = m.groups()
		if q is not None:
			tokens.append(re.sub(r"\\(.)", r"\1", q))
		else:
			tokens.append(u)
	return tokens


def parse_append_header(args_str):
	m = re.search(r"\{(\d+)\}\s*$", args_str)
	if not m:
		return None
	lit_len = int(m.group(1))
	
	prefix = args_str[: m.start()].strip()
	m_box = re.match(r'^(?:"([^"\\]*(?:\\.[^"\\]*)*)"|(\S+))', prefix)
	if not m_box:
		return None
	
	mailbox_name = (
		m_box.group(1) if m_box.group(1) is not None else m_box.group(2)
	)
	if m_box.group(1) is not None:
		mailbox_name = re.sub(r"\\(.)", r"\1", mailbox_name)
	
	return mailbox_name, lit_len


def imap_fnmatch(name, pattern, delim="/"):
	if not pattern:
		return False
	regex = "^"
	for char in pattern:
		if char == "*":
			regex += ".*"
		elif char == "%":
			regex += f"[^{re.escape(delim)}]*"
		else:
			regex += re.escape(char)
	regex += "$"
	return re.match(regex, name, re.IGNORECASE) is not None


def filter_header_fields(raw_msg_bytes, fields_list):
	sep = b"\r\n\r\n" if b"\r\n\r\n" in raw_msg_bytes else b"\n\n"
	hdr_part = (
		raw_msg_bytes.split(sep, 1)[0] if sep in raw_msg_bytes else raw_msg_bytes
	)
	
	lines = (
		hdr_part.decode("utf-8", errors="replace")
		.replace("\r\n", "\n")
		.split("\n")
	)
	fields_lower = [f.strip().lower() for f in fields_list]
	
	result_lines = []
	matching = False
	for line in lines:
		if line.startswith(" ") or line.startswith("\t"):
			if matching:
				result_lines.append(line)
		else:
			if ":" in line:
				key = line.split(":", 1)[0].strip().lower()
				if key in fields_lower:
					matching = True
					result_lines.append(line)
				else:
					matching = False
			else:
				matching = False
	
	res_str = "\r\n".join(result_lines)
	if res_str:
		res_str += "\r\n"
	res_str += "\r\n"
	return res_str.encode("utf-8")


def parse_sequence_set(seq_set_str, total_items, uids=None):
	if total_items == 0:
		return []
	
	indices = set()
	parts = seq_set_str.split(",")
	
	for part in parts:
		part = part.strip()
		if not part:
			continue
		
		if ":" in part:
			start_str, end_str = part.split(":", 1)
			if uids is not None:
				min_uid = uids[0] if uids else 1
				max_uid = uids[-1] if uids else total_items
				
				s_uid = min_uid if start_str == "*" else int(start_str)
				e_uid = max_uid if end_str == "*" else int(end_str)
				if s_uid > e_uid:
					s_uid, e_uid = e_uid, s_uid
				
				for idx, uid in enumerate(uids):
					if s_uid <= uid <= e_uid:
						indices.add(idx)
			else:
				s_seq = 1 if start_str == "*" else int(start_str)
				e_seq = total_items if end_str == "*" else int(end_str)
				if s_seq > e_seq:
					s_seq, e_seq = e_seq, s_seq
				
				s_idx = max(0, s_seq - 1)
				e_idx = min(total_items, e_seq)
				for idx in range(s_idx, e_idx):
					indices.add(idx)
		else:
			if part == "*":
				indices.add(total_items - 1)
			elif part.isdigit():
				val = int(part)
				if uids is not None:
					if val in uids:
						indices.add(uids.index(val))
				else:
					idx = val - 1
					if 0 <= idx < total_items:
						indices.add(idx)
	
	return sorted(list(indices))


class IMAPHandler(socketserver.StreamRequestHandler):
	def handle(self):
		self.authenticated = False
		self.current_folder = "INBOX"
		self.current_folder_path = None
		self.selected_msg_count = 0
		self.send_line("* OK Simple IMAP Server Ready")
		
		while True:
			line = self.rfile.readline()
			# print(">", line)
			if not line:
				break
			
			cmd_line = line.decode("utf-8", errors="replace").strip()
			if not cmd_line:
				continue
			
			parts = cmd_line.split(" ", 2)
			tag = parts[0]
			if len(parts) < 2:
				self.send_line(f"{tag} BAD Invalid command format")
				continue
			
			cmd = parts[1].upper()
			args_str = parts[2] if len(parts) > 2 else ""
			
			if cmd == "CAPABILITY":
				self.send_line("* CAPABILITY IMAP4rev1 LOGIN")
				self.send_line(f"{tag} OK CAPABILITY completed")
			
			elif cmd == "LOGIN":
				tokens = parse_imap_args(args_str)
				if (
					len(tokens) >= 2
					and tokens[0] == self.server.user
					and tokens[1] == self.server.password
				):
					self.authenticated = True
					self.send_line(f"{tag} OK LOGIN completed")
				else:
					self.send_line(f"{tag} NO LOGIN failed")
			
			elif not self.authenticated:
				self.send_line(f"{tag} NO Authenticate first")
			
			elif cmd in ("LIST", "LSUB"):
				tokens = parse_imap_args(args_str)
				ref = tokens[0] if len(tokens) > 0 else ""
				pattern = tokens[1] if len(tokens) > 1 else "*"
				
				if pattern == "":
					self.send_line('* LIST (\\Noselect) "/" ""')
				else:
					folders = self.get_available_folders()
					all_folder_names = list(folders.keys())

					for folder_name in all_folder_names:
						if (
							folder_name != "INBOX"
							and folder_name.startswith("INBOX/")
						):
							continue
						
						if imap_fnmatch(folder_name, pattern):
							prefix = folder_name + "/"
							has_children = any(
								other.startswith(prefix)
								for other in all_folder_names
								if other != folder_name
							)
							flags = (
								"(\\HasChildren)"
								if has_children
								else "(\\HasNoChildren)"
							)

							self.send_line(
								f'* {cmd} {flags} "/" "{folder_name}"'
							)
				
				self.send_line(f"{tag} OK {cmd} completed")

			elif cmd in ("SELECT", "EXAMINE"):
				tokens = parse_imap_args(args_str)
				target_folder = tokens[0] if tokens else "INBOX"
				
				folders = self.get_available_folders()
				matched_path = folders.get(target_folder) or folders.get(
					target_folder.strip('"')
				)
				
				if not matched_path:
					self.send_line(f"{tag} NO Mailbox does not exist")
					continue
				
				self.current_folder = target_folder
				self.current_folder_path = matched_path
				self.reload_mailbox(matched_path)
				self.selected_msg_count = len(self.msg_keys)

				self.send_line(f"* {self.selected_msg_count} EXISTS")
				self.send_line("* 0 RECENT")
				self.send_line("* OK [UIDVALIDITY 1]")
				self.send_line(f"* OK [UIDNEXT {self.selected_msg_count + 1}]")
				self.send_line(
					"* FLAGS (\\Answered \\Flagged \\Deleted \\Seen"
					" \\Draft)"
				)
				self.send_line(
					"* OK [PERMANENTFLAGS (\\Answered \\Flagged \\Deleted"
					" \\Seen \\Draft)]"
				)
				self.send_line(f"{tag} OK [READ-WRITE] {cmd} completed")
			
			elif cmd == "APPEND":
				if not self.server.enable_append:
					self.send_line(f"{tag} NO APPEND command is disabled")
					continue
				
				parsed_append = parse_append_header(args_str)
				if not parsed_append:
					self.send_line(f"{tag} BAD Invalid APPEND syntax")
					continue
				
				target_folder, lit_len = parsed_append
				folders = self.get_available_folders()
				matched_path = folders.get(target_folder) or folders.get(
					target_folder.strip('"')
				)
				
				if not matched_path:
					if (
						self.server.enable_subfolders
						and target_folder.upper() != "INBOX"
					):
						clean_name = target_folder
						if clean_name.upper().startswith("INBOX/"):
							clean_name = clean_name[6:]
						clean_name = clean_name.replace("/", ".")
						if not clean_name.startswith("."):
							clean_name = "." + clean_name
						matched_path = os.path.join(
							self.server.maildir_path, clean_name
						)
					else:
						matched_path = (
							self.server.maildir_path
							if target_folder.upper() == "INBOX"
							else None
						)
				
				if not matched_path:
					self.send_line(
						f"{tag} NO [TRYCREATE] Mailbox does not exist"
					)
					continue
				
				self.send_line("+ Ready for literal data")
				
				msg_bytes = self.rfile.read(lit_len)
				
				for sub in ["cur", "new", "tmp"]:
					os.makedirs(os.path.join(matched_path, sub), exist_ok=True)
				mbox = mailbox.Maildir(matched_path)
				mbox.add(msg_bytes)
				
				self.send_line(f"{tag} OK APPEND completed")
			
			elif cmd in ("SUBSCRIBE", "UNSUBSCRIBE"):
				self.send_line(f"{tag} OK {cmd} completed")
			
			elif cmd == "NOOP":
				if self.current_folder_path and os.path.exists(
					self.current_folder_path
				):
					self.reload_mailbox(self.current_folder_path)
					new_count = len(self.msg_keys)
					if new_count > self.selected_msg_count:
						diff = new_count - self.selected_msg_count
						self.send_line(f"* {new_count} EXISTS")
						self.send_line(f"* {diff} RECENT")
						self.selected_msg_count = new_count
					elif new_count < self.selected_msg_count:
						self.send_line(f"* {new_count} EXISTS")
						self.selected_msg_count = new_count

				self.send_line(f"{tag} OK NOOP completed")
			
			elif cmd in ("FETCH", "UID"):
				folders = self.get_available_folders()
				folder_path = folders.get(
					self.current_folder, self.server.maildir_path
				)
				self.reload_mailbox(folder_path)
				
				req_args = args_str
				is_uid_cmd = cmd == "UID"
				if is_uid_cmd and req_args.upper().startswith("FETCH "):
					req_args = req_args[6:].strip()
				
				fetch_parts = req_args.split(" ", 1)
				seq_range = fetch_parts[0]
				requested_items = (
					fetch_parts[1].upper() if len(fetch_parts) > 1 else ""
				)
				
				uids = [i + 1 for i in range(len(self.msg_keys))]
				indices = parse_sequence_set(
					seq_range,
					len(self.msg_keys),
					uids=uids if is_uid_cmd else None,
				)
				
				for idx in indices:
					key = self.msg_keys[idx]
					raw_msg = self.mbox[key].as_bytes()
					raw_msg = raw_msg.replace(b"\r\n", b"\n").replace(
						b"\n", b"\r\n"
					)
					
					uid = idx + 1
					seq = idx + 1
					size = len(raw_msg)
					
					body_match = re.search(
						r"BODY(?:\.PEEK)?(\[[^\]]*\])",
						fetch_parts[1],
						re.IGNORECASE,
					)
					
					if body_match:
						section = body_match.group(1)
						attr_name = f"BODY{section}"
						
						fields_match = re.search(
							r"HEADER\.FIELDS\s*\(([^)]+)\)",
							section,
							re.IGNORECASE,
						)
						
						if fields_match:
							field_names = fields_match.group(1).split()
							content = filter_header_fields(
								raw_msg, field_names
							)
						elif "HEADER" in section:
							sep = b"\r\n\r\n"
							content = (
								raw_msg.split(sep, 1)[0] + sep
								if sep in raw_msg
								else raw_msg
							)
						elif "TEXT" in section:
							sep = b"\r\n\r\n"
							content = (
								raw_msg.split(sep, 1)[1]
								if sep in raw_msg
								else b""
							)
						else:
							content = raw_msg
						
						content_len = len(content)
						
						self.send_line(
							f"* {seq} FETCH (UID {uid} FLAGS (\\Seen)"
							f" RFC822.SIZE {size} {attr_name} {{{content_len}}}"
						)
						self.wfile.write(content + b")\r\n")
						self.wfile.flush()
					
					elif (
						"RFC822" in requested_items
						and "RFC822.SIZE" not in requested_items
					):
						self.send_line(
							f"* {seq} FETCH (UID {uid} FLAGS (\\Seen) RFC822"
							f" {{{size}}}"
						)
						self.wfile.write(raw_msg + b")\r\n")
						self.wfile.flush()
					
					else:
						self.send_line(
							f"* {seq} FETCH (UID {uid} FLAGS (\\Seen)"
							f" RFC822.SIZE {size})"
						)
				
				self.send_line(f"{tag} OK {cmd} completed")
			
			elif cmd == "LOGOUT":
				self.send_line("* BYE IMAP4rev1 Server logging out")
				self.send_line(f"{tag} OK LOGOUT completed")
				break
			
			else:
				self.send_line(f"{tag} BAD Command not supported")

	def get_available_folders(self):
		root_dir = self.server.maildir_path
		folders = {"INBOX": root_dir}
		
		if not self.server.enable_subfolders or not os.path.exists(root_dir):
			return folders
		
		for root, dirs, files in os.walk(root_dir):
			dirs[:] = [d for d in dirs if d not in ("cur", "new", "tmp")]
			
			for d in dirs:
				full_path = os.path.join(root, d)
				rel_path = os.path.relpath(full_path, root_dir)
				
				folders[rel_path] = full_path
				folders[f"INBOX/{rel_path}"] = full_path
		
		return folders
	
	def reload_mailbox(self, path):
		self.mbox = mailbox.Maildir(path)
		self.msg_keys = sorted(list(self.mbox.keys()))
	
	def send_line(self, text):
		# print("<", text)
		self.wfile.write((text + "\r\n").encode("utf-8"))
		self.wfile.flush()


class ThreadedIMAPServer(socketserver.ThreadingTCPServer):
	allow_reuse_address = True
	address_family = socket.AF_INET6
	
	def server_bind(self):
		self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
		super().server_bind()


def main():
	parser = argparse.ArgumentParser(
		description="Prosty jednoutkownikowy serwer IMAP Maildir."
	)
	parser.add_argument("-d", "--dir", required=True, help="Ścieżka do Maildir")
	parser.add_argument("-u", "--user", default="imap")
	parser.add_argument("-p", "--pass", dest="password", default="secret")
	parser.add_argument("-H", "--host", default="::1")
	parser.add_argument("-P", "--port", type=int, default=1143)
	parser.add_argument( "--no-append", action="store_true", help="Wyłącza obsługę polecenia APPEND (dodawanie wiadomości)" )
	parser.add_argument( "--no-subfolders", action='store_true', help="Wyłącza obsługę podfolderów Maildir" )
	
	args = parser.parse_args()
	
	server = ThreadedIMAPServer((args.host, args.port), IMAPHandler)
	server.maildir_path = args.dir
	server.user = args.user
	server.password = args.password
	server.enable_subfolders = not args.no_subfolders
	server.enable_append = not args.no_append
	
	print(
		f"Serwer IMAP uruchomiony na {args.host}:{args.port} (subfolders: {server.enable_subfolders}, append: {server.enable_append})"
	)
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass


if __name__ == "__main__":
	main()
