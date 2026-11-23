---
layout: post
title: Szyfrowany git
author: Robert Paciorek
tags:
- git
- kryptografia
---

Do zagadnienia szyfrowania repozytorium git lub tez danych w takim repozytorium można podejść na kilka sposobów.

### szyfrowanie wybranych plików

Pakiet `git-crypt` pozwala na szyfrowanie wybranych plików.
Pliki które mają być szyfrowane określa się w pliku `.gitattributes` (np. `*.key filter=git-crypt diff=git-crypt` spowoduje szyfrowanie plików z rozszerzeniem `.key`).
Szyfrowaniu będą podlegałby pliki dodane do repozytorium po skonfigurowaniu `git-crypt`.

`git-crypt` potrafi korzystać z kluczy gpg poprzez `git-crypt add-gpg-user` (dodanie wskazanego klucza) i `git-crypt unlock` (odblokowanie moim kluczem, musi być wcześniej dodany).

Rozwiązanie to nie zapewnia szyfrowania opisów commitów oraz powoduje trzymanie plików binarnych w repozytorium (większy rozmiar repozytorium niż przy plikach tekstowych).


### szyfrowanie wybranych remote dla repozytorium

#### git-remote-gcrypt

Pakiet `git-remote-gcrypt` pozwala na szyfrowanie całości repozytorium dla danego remote.
Konfiguracja odbywa się poprzez dodanie remote jako `gcrypt::` (np. `gcrypt::ssh://` lub `gcrypt::rsync://`).
Dodatkowo przydatne mogą być opcje konfiguracyjne:

* `git config --global gcrypt.publish-participants true` (zapisuje jawnie ID kluczy pozwalających na odszyfrowanie, dzięki czemu gpg nie musi sprawdzać wszystkich),
* `git config --global gcrypt.require-explicit-force-push true` (wymaga jawnego `--force` w operacjach push).

Wadą takiego rozwiązania jest robienie każdego push jako `--force` (zobacz związany z tym [bug](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=877464)) oraz każdorazowe szyfrowanie całości repozytorium.
Rozwiązanie to nie zaszyfruje także plików lfs, przynajmniej tych wysyłanych bez wsparcia po stronie serwera (z użyciem [`git-lfs-standalonetransfer-ssh`](/2026/09/23/git_lfs.html)).


#### lokalne montowanie z szyfrowaniem zdalnego zasobu (z użyciem gocryptfs i sshfs)

Innym podejściem może być lokalne zamontowanie zdalnego zasobu (np. z użyciem sshfs), nałożenie na niego lokalnej warstwy szyfrującej na poziomie pojedynczych plików (np. gocryptfs) i użycie lokalnego push do tego zasobu.

Zaleta takiego podejścia jest to, iż dla git'a jest to całkowicie normalne repozytorium (unikamy wszystkich problemów z danymi binarnymi, wymuszonymi push'am, czy koniecznością każdorazowego szyfrowania całości).
Dodatkowo zamiast sshfs można użyć innych typów zdalnych zasobów (np. za pośrednictwem rclone).

##### git-remote-cryptossh.sh

Podejście takie da się w pełni zautomatyzować stosując własny protokół remote dla tego typu zasobów.

Przykładowa implementacja zawarta jest w [/files/git-remote-cryptossh.sh](git-remote-cryptossh.sh). Uwaga: ze względu na sposób wyszukiwania programów obsługujących protokoły remote przez git skrypt ten musi być zapisany w katalogu ścieżki wyszukiwania dokładnie pod nazwą `git-remote-cryptossh` (bez rozszerzenia).

Skrypt ten obsługuje inicjalnizację takiego zdalnego remote poprzez wywołanie `git-remote-cryptossh init origin user@host:port/path/to/repo`.
Git będzie używał go dla operacji push i fetch/pull związanych z remote których protokół jest `cryptossh://`. Dla każdej takiej operacji nastąpi:

1. zamontowanie i odszyfrowanie zdalnego repozytorium (w `.git/remote_fs/$REMOTE_NAME/decrypted`)
2. wykonanie operacji transferu plików zleconych przez git (obejmie to także pliki z .git/lfs/objects, bez potrzeby korzystania z jakichkolwiek dodatkowych programów do obsługi lfs via ssh)
3. odmontowanie zdalnego zasobu

Hasło dla klucza szyfrującego trzymane jest w `.git/remote_fs/$REMOTE_NAME/.pass` – założeniem jest że miejsce w którym trzymamy odszyfrowaną wersję repo jest na bezpiecznym storage.

##### wady i potencjalne problemy

Wadą takiego podejścia są potencjalne problemy związane z używaniem repozytorium git na zamontowanym zdalnym zasobie.
W szczególności potencjalny problem wyścigu przy równoległych push przez wiele osób (związany z brakiem flock na sshfs i opóźnieniami które mogą być problematyczne dla systemu blokowania git'a).
Problem ten można rozwiązać obejmując cały ten skrypt globalnym lockiem - patrz [lock_over_ssh.sh](files/lock_over_ssh.sh).

Innym problemem jest powolne działanie, zwłaszcza gdy ping do serwera trzymającego taki remote jest znaczny (co znacznie spowalnia listowanie zasobów SFTP).


### szyfrowany backup zamiast remote

Jeszcze innym podejściem jest po prostu utworzenie zdalnej szyfrowanej kopii zapasowej repozytorium (samego `.git` lub także z kopią roboczą). Można do tego użyć np. [restic](https://restic.net/).
Dzięki wbudowanej deduplikacji dobrze radzi sobie z przypadkiem gdy backupuje także kopię roboczą a repo git używa annex lub lfs i te same duże pliki znajdują się w obu miejscach.

[Skrypt backupujący](/files/git2restic.sh) wykorzystujący konfig z repozytorium i jego nazwę na potrzeby tworzonego backupu.
