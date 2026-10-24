#!/bin/bash
set -e

if [ "$1" = "quiet" ]; then
	vlog() { : "$@"; }
else
	vlog() { echo "$@"; }
fi

set_vars() {
	CONTAINER_ID="$1"
	
	# Wygeneruj unikalne nazwy dla interfejsów veth
	SHORT_ID=$(echo "$CONTAINER_ID" | cut -c1-6)
	VETH_HOST="docker-$SHORT_ID"
	VETH_GUEST="vguest-$SHORT_ID"
}

start_net() {
	set_vars $1
	
	# Nazwa urządzenia bridge'a
	BRIDGE="${2:-br0}"
	
	# PID kontenera
	PID=$(docker inspect -f '{{.State.Pid}}' "$CONTAINER_ID")
	
	# Adres IP dla kontenera (dhcp gdy pusty)
	IP=$(docker inspect -f '{{index .Config.Labels "custom.ne"}}' "$CONTAINER_ID")
	
	if [ -d "/sys/class/net/$VETH_HOST" ]; then
		echo "ERROR: can't create interface $VETH_HOST for $PID/$CONTAINER_ID - already exist"
		exit 1
	fi
	
	vlog "  - tworze parę urządzeń veth"
	ip link add "$VETH_HOST" type veth peer name "$VETH_GUEST"
	
	vlog "  - przypisuję $VETH_HOST do systemowego mostka $BRIDGE i podnosze go"
	ip link set "$VETH_HOST" master "$BRIDGE"
	ip link set "$VETH_HOST" up
	
	vlog "  - przenoszę drugi koniec pary veth do przestrzeni nazw (network namespace) kontenera Dockerowego"
	ip link set "$VETH_GUEST" netns "$PID"
	
	vlog "  - podnoszę interfejs wewnątrz kontenera"
	nsenter -t $PID -n ip link set "$VETH_GUEST" up
	
	vlog "  - konfiguruję interfejsu wewnątrz kontenera (${IP:-dhcp})"
	if [ "$IP" = "" ]; then
		nsenter -t $PID -n dhclient "$VETH_GUEST" || nsenter -t $PID -n udhcpc -i "$VETH_GUEST"
	else
		nsenter -t $PID -n ip addr add "$VETH_GUEST" "$IP"
	fi
}

stop_net() {
	set_vars $1
	
	# usuwanie pary veth związanej z zakończonym kontenerem
	vlog "  - usuwam parę urządzeń veth (poprzez usunięcie $VETH_HOST)"
	if [ -d "/sys/class/net/$VETH_HOST" ]; then
		ip link del "$VETH_HOST"
	else
		echo "      Nie można usunąć: $VETH_HOST nie istnieje"
	fi
}

cleanup_and_stop() {
	echo "Stopping docker ..."
	
	# sprzątanie po obsłudze sieci
	for CONTAINER_ID in $(docker ps -q --no-trunc); do
		stop_net $CONTAINER_ID
	done

	# zatrzymywanie dockera
	systemctl stop containerd.service docker.service docker.socket
}

trap cleanup_and_stop EXIT


# uruchomienie dockera
systemctl start docker
echo "Docker is ready"

# obsługa sieci
docker events --filter "event=start" --filter "event=die" --format "{{.Status}} {{.ID}}" | while read -r STATUS CONTAINER_ID; do
	echo " -> $CONTAINER_ID $STATUS"
	case $STATUS in
		start) start_net $CONTAINER_ID ;;
		die) stop_net $CONTAINER_ID ;;
	esac
done
