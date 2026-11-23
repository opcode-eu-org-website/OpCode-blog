/*
SPDX-FileCopyrightText: Robert Ryszard Paciorek <rrp@opcode.eu.org>
SPDX-License-Identifier: MIT

created by Gemini AI, 2026

Instrukcja użycia:
  * Wejdź na stronę Google Apps Script i kliknij Start Scripting (zaloguj się tym samym kontem Gmail).
  * Kliknij Nowy projekt.
  * Usuń domyślny kod i wklej powyższy skrypt:
  * Zastąp ADRES@DO.POWIADOMIEN adresem, na który mają trafiać powiadomienia.
  * Kliknij ikonę dyskietki (Zapisz), a następnie kliknij ikonę zegara po lewej stronie (Wyzwalacze).
  * Dodaj nowy wyzwalacz: ustaw uruchamianie funkcji sendEmailNotification jako „Zarządzane czasem” (np. co 5, 10 lub 15 minut).
*/

function sendEmailNotification() {
  // Kasujemy wysłane
  var wyslane = GmailApp.search('in:sent');
  if (wyslane.length > 0) {
    GmailApp.moveThreadsToTrash(wyslane);
  }

  // Szuka nieprzeczytanych wiadomości w odebranych
  var threads = GmailApp.search('is:unread in:inbox');
  var targetEmail = "ADRES@DO.POWIADOMIEN";
  
  for (var i = 0; i < threads.length; i++) {
    var messages = threads[i].getMessages();
    var lastMessage = messages[messages.length - 1];
    
    if (lastMessage.isUnread()) {
      var subject = lastMessage.getSubject();
      var sender = lastMessage.getFrom();
      
      // Wysyła maila TYLKO z tematem i nadawcą
      MailApp.sendEmail({
        to: targetEmail,
        subject: sender + " -- " + subject,
        body: "Otrzymałeś nową wiadomość.\nTemat: " + subject + "\nNadawca: " + sender + "\nAdresat: " + lastMessage.getTo()
      });
      
      // Oznacza wiadomość jako przeczytaną, aby nie wysyłać powiadomienia ponownie
      lastMessage.markRead();
    }
  }
}
