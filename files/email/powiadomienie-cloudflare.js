/*
SPDX-FileCopyrightText: Robert Ryszard Paciorek <rrp@opcode.eu.org>
SPDX-License-Identifier: MIT

created by Gemini AI, 2026

Worker realizujący powiadomienie i forward wiadomości e-mail.

W konfiguracji workera należy ustawić binding do usługi email z nazwą `SEND_EMAIL` i przekierować maile do tego wrokera.

Jeżeli adresy GLOWNY_EMAIL i EMAIL_POWIADOMIENIA są naszymi zweryfikowanymi adresami, to nie wymaga to aktywnej usługi wysyłania maili w cloudflare.
*/

export default {
  async email(message, env, ctx) {
    const GLOWNY_EMAIL = "ADRES@DO.FORWARDU";
    const EMAIL_POWIADOMIENIA = "ADRES@DO.POWIADOMIEN";

    const temat = message.headers.get("subject") || "(Brak tematu)";
    const nadawca = message.from;
    const oryginalnyOdbiorca = message.to;

    await message.forward(GLOWNY_EMAIL);

    await env.SEND_EMAIL.send({
      to: EMAIL_POWIADOMIENIA,
      from: oryginalnyOdbiorca,
      subject: `${nadawca} -- ${temat}`,
      text: `Otrzymałeś nową wiadomość.\n\nOd: ${nadawca}\nTemat: ${temat}\nOdbiorca: ${oryginalnyOdbiorca}\n\nPełna treść została przesłana na skrzynkę główną.`
    });
  }
};
