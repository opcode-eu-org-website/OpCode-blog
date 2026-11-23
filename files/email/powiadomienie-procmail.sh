#!/bin/bash

head=`cat | formail -X "Subject:" -X "From:"`
from=`echo "$head" | formail -xFrom:`
subj=`echo "$head" | formail -xSubject:`

if  echo "" | mail -s "$from -- $subj" ADRES@DO.POWIADOMIEN; then
	echo OK
	exit 0
else
	echo ERR
	exit 1
fi
