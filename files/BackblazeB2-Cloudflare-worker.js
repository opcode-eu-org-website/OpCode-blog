/*
SPDX-FileCopyrightText: Robert Ryszard Paciorek <rrp@opcode.eu.org>
SPDX-License-Identifier: MIT

Created with Gemini AI, 2026


Worker dla Cloudflare do proxy własna domena -> prywatny bucket S3.


Wdrożenie workera:

1. W ustawieniach Workera (Settings -> Variables and Secrets) dodaj swoje zmienne:
	• B2_BUCKET_NAME (nazwa prywatnego bucketa)
	• B2_ENDPOINT (np. s3.eu-central-003.backblazeb2.com)
	• B2_APPLICATION_KEY_ID (Twój keyID)
	• B2_APPLICATION_KEY (Twój applicationKey jako Secret)
2. Podepnij pod Workera swoją subdomenę (np. assets.twojadomena.pl) w zakładce Settings -> Domains & Routes lub użyj darmowego adresu *.workers.dev.

*/

export default {
  async fetch(request, env, ctx) {
    // 1. Zezwalamy tylko na bezpieczne metody odczytu (GET i HEAD dla git-annex)
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const url = new URL(request.url);
    
    // Odrzucamy puste żądania do katalogu głównego
    if (url.pathname === '/' || url.pathname === '') {
      return new Response('Blender Assets CDN (git-annex remote)', { status: 200 });
    }

    // 2. Sprawdzenie pamięci podręcznej Cloudflare (Cache API)
    const cache = caches.default;
    const cacheKey = new Request(url.toString(), { method: 'GET' });
    let cachedResponse = await cache.match(cacheKey);
    if (cachedResponse) {
      if (request.method === 'HEAD') {
        return new Response(null, {
          status: cachedResponse.status,
          statusText: cachedResponse.statusText,
          headers: cachedResponse.headers
        });
      }
      return cachedResponse;
    }

    // 3. Przygotowanie żądania do prywatnego bucketa Backblaze B2 (Path Style)
    const targetUrl = new URL(`/${env.B2_BUCKET_NAME}${url.pathname}${url.search}`, `https://${env.B2_ENDPOINT}`);
    const region = env.B2_ENDPOINT.split('.')[1] || 'eu-central-003';

    // 4. Podpisanie żądania algorytmem AWS Signature V4
    const signedHeaders = await signAwsV4({
      method: request.method,
      url: targetUrl,
      region: region,
      service: 's3',
      accessKeyId: env.B2_APPLICATION_KEY_ID,
      secretAccessKey: env.B2_APPLICATION_KEY
    });

    const b2Response = await fetch(targetUrl.toString(), {
      method: request.method,
      headers: signedHeaders
    });

    // 5. Przetworzenie odpowiedzi i zapis do Cache Cloudflare
    const responseHeaders = new Headers(b2Response.headers);
    
    // Usuwamy wewnętrzne nagłówki Backblaze
    for (const key of [...responseHeaders.keys()]) {
      if (key.toLowerCase().startsWith('x-bz-')) {
        responseHeaders.delete(key);
      }
    }

    // Ustawiamy długi czas buforowania (1 rok), ponieważ klucze git-annex są niezmienne (oparte o sumy kontrolne)
    if (b2Response.ok) {
      responseHeaders.set('Cache-Control', 'public, max-age=31536000, immutable');
      responseHeaders.set('Access-Control-Allow-Origin', '*');
    }

    const finalResponse = new Response(b2Response.body, {
      status: b2Response.status,
      statusText: b2Response.statusText,
      headers: responseHeaders
    });

    // Zapisujemy w cache tylko pełne odpowiedzi GET (bez żądań częściowych Range 206)
    if (request.method === 'GET' && b2Response.status === 200) {
      ctx.waitUntil(cache.put(cacheKey, finalResponse.clone()));
    }

    return finalResponse;
  }
};

// --- Funkcje pomocnicze do podpisu AWS Signature V4 (Web Crypto API) ---

async function signAwsV4({ method, url, region, service, accessKeyId, secretAccessKey }) {
  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, '');
  const dateStamp = amzDate.slice(0, 8);
  const payloadHash = 'UNSIGNED-PAYLOAD';

  const canonicalUri = url.pathname.split('/').map(encodeURIComponent).join('/').replace(/%2F/g, '/');
  const canonicalQuerystring = [...url.searchParams.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');

  const headers = {
    'host': url.host,
    'x-amz-content-sha256': payloadHash,
    'x-amz-date': amzDate
  };

  const sortedHeaderKeys = Object.keys(headers).sort();
  const canonicalHeaders = sortedHeaderKeys.map(k => `${k}:${headers[k]}\n`).join('');
  const signedHeaders = sortedHeaderKeys.join(';');

  const canonicalRequest = [
    method,
    canonicalUri,
    canonicalQuerystring,
    canonicalHeaders,
    signedHeaders,
    payloadHash
  ].join('\n');

  const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;
  const stringToSign = [
    'AWS4-HMAC-SHA256',
    amzDate,
    credentialScope,
    await sha256Hex(canonicalRequest)
  ].join('\n');

  const signingKey = await getSignatureKey(secretAccessKey, dateStamp, region, service);
  const signature = await hmacHex(signingKey, stringToSign);

  headers['Authorization'] = `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;
  return headers;
}

async function sha256Hex(message) {
  const data = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(hashBuffer)].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function hmacRaw(key, message) {
  const keyData = typeof key === 'string' ? new TextEncoder().encode(key) : key;
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  return await crypto.subtle.sign('HMAC', cryptoKey, new TextEncoder().encode(message));
}

async function hmacHex(key, message) {
  const sig = await hmacRaw(key, message);
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function getSignatureKey(key, dateStamp, regionName, serviceName) {
  const kDate = await hmacRaw('AWS4' + key, dateStamp);
  const kRegion = await hmacRaw(kDate, regionName);
  const kService = await hmacRaw(kRegion, serviceName);
  return await hmacRaw(kService, 'aws4_request');
}
