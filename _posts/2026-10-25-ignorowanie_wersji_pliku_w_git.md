---
layout: post
title: Ignorowanie konkretnej wersji pliku w git
author: Robert Paciorek
tags:
- git
---

Git pozwala standardowo na ignorowanie pliku na dwa sposoby:

1. plik `.gitignore` - określone w nim pliki nie będą pojawiały się na liście nieśledzonych plików w `git status`, ich dodanie do repo będzie wymagało użycia opcji `-f`, ale po dodaniu do repo kolejne zmiany w nich będą śledzone
2. polecenie `git update-index --skip-worktree` - spowoduje wyłączenie śledzenia wskazanego pliku z kopii roboczej, do czasu ponownego włączenia zmiany w tym pliku nie będą pokazywane w `git status` ani uwzględniane w `commit -a`

Często jednak zachodzi potrzeba zignorowania jedynie konkretnych zmian (np. w pliku konfiguracyjnym) lub konkretnej wersji danego pliku. W taki sposób aby wprowadzenie w nim kolejnych/innych zmian oznaczyło go ponownie jako zmodyfikowany w `git status` (dzięki czemu nie ma problemu zapomnienia o tym że na pliku zostało ustawione *skip-worktree*).

## Filtry Git'a

Można to uzyskać z użyciem mechnizmu filtrów git'a.

* `git config filter.my_filter.clean 'POLECENIE "%f"'` - ustawia polecenie które przefiltruje (na swoim stdin → stdout) zawartość pliku kopii roboczej porównywanego z repozytorium (przesyłanego do niego)
* `git config filter.my_filter.smudge 'POLECENIE "%f"'` - ustawia polecenie które przefiltruje (na swoim stdin → stdout) zawartość pliku repozytorium porównywanego z kopią roboczą (wypakowywanego do niej)

W obu wypadkach można użyć `%f` aby pozyskać informację o ścieżce pliku (ale przetwarzać należy standardowe wejście na standardowe wyjście a nie treść pliku wskazanego przez `%f`).

Pliki do filtrowania danym filtrem (w tym przykładzie `my_filter`) określa się wpisami w `.gitattributes` (lub `.git/info/attributes` jeżeli ustawienia mają być lokalne) postaci: `GLOB_OKREŚLAJĄCY_PLIK filter=my_filter`.

### Zastosowania

Pozwala to na zautomatyzowanie / ukrycie konkretnej zmiany (gdy np. w obu poleceniach zostanie użyty sed o odwrotnym działaniu).

Można z pomocą tego mechanizmu śledzić też całą zawartość pliku i uznawać z niezmodyfikowaną (równą sobie) jedynie konkretną parę wersji repozytorium - kopia robocza.
Taki scenariusz realizuje skrypt [git_local_ignore.sh](/files/git_local_ignore.sh). Przykład użycia:

	# koniguracja filtru (raz na repozytorium)
	git config filter.my_ignore.clean "git_local_ignore.sh clean '%f'"
	git config filter.my_ignore.smudge "git_local_ignore.sh smudge '%f'
	
	# konfiguracja pliku do ignorowania
	git show HEAD:PLIK_DO_IGNOROWANIA > "$(git rev-parse --git-dir)/ignored/repo/PLIK_DO_IGNOROWANIA"
	cp PLIK_DO_IGNOROWANIA "$(git rev-parse --git-dir)/ignored/local/PLIK_DO_IGNOROWANIA"
	echo "PLIK_DO_IGNOROWANIA filter=my_ignore" >> "$(git rev-parse --git-dir)/info/attributes"
