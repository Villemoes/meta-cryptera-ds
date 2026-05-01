#!/bin/bash

set -e
umask 0077

err() {
    printf "%s\n" "$*" >&2
    exit 1
}

curl() {
    local method="$1"
    local url="$2"
    shift 2

    command curl --silent --show-error --tlsv1.3 --request "$method" \
            --header "Accept: application/json" \
            "$@" "$url"
}

help() {
    cat <<EOF
Usage: get_public_keys.sh [options] [<key-id> [<key-id>...]]

Retrieve the public keys (certificates) corresponding to the keys with
the given key-ids. If no key-ids are given, retrieves the public keys
for all keys for which the user/client has permissions.

Each public key is written to the file <key-id>.pem in the output
directory.

The CRYPTERA_ID_TOKEN environment variable is expected to contain a
valid authentication token. Alternatively, one can obtain such a token
from an authentication server by setting environment variables
CRYPTERA_ID_USER/CRYPTERA_ID_PASSWD, or supplying those interactively.

Options:

  --output-dir <dir>    Write files to this directory (default: .)
  --key-server <url>    Server to contact for obtaining the public keys
                        (default: CRYPTERA_KEYSERVER environment variable)
  --auth-server <url>   Server to use for obtaining authentication token
                        (default: CRYPTERA_AUTHSERVER environment variable)

EOF
}

output_dir=.

while [ "$#" -gt 0 ] ; do
    case "$1" in
        (--output-dir=*)  output_dir="${1#*=}" ; shift 1 ; continue ;;
        (--output-dir)    output_dir="${2:?Missing argument to --output-dir}" ; shift 2 ; continue ;;
        (--auth-server=*) CRYPTERA_AUTHSERVER="${1#*=}" ; shift 1 ; continue ;;
        (--auth-server)   CRYPTERA_AUTHSERVER="${2:?Missing argument to --auth-server}" ; shift 2 ; continue ;;
        (--key-server=*)  CRYPTERA_KEYSERVER="${1#*=}" ; shift 1 ; continue ;;
        (--key-server)    CRYPTERA_KEYSERVER="${2:?Missing argument to --key-server}" ; shift 2 ; continue ;;
        (--help)          help ; exit 0 ;;
        (-*)              err "Unknown option $1"  ;;
        (*)               break ;;
    esac
done

tmpd="$(mktemp -d)"

trap finish EXIT
# shellcheck disable=SC2317 # invoked via trap EXIT
finish() {
    rm -rf "${tmpd}"
}

if [ -z "${CRYPTERA_ID_TOKEN}" ] ; then
    [ -n "${CRYPTERA_AUTHSERVER}" ] || err "No CRYPTERA_ID_TOKEN and no authserver known, pass --authserver=<url> or export CRYPTERA_AUTHSERVER"

    echo "Will obtain ID token from ${CRYPTERA_AUTHSERVER} using username/password."
    if [ -z "${CRYPTERA_ID_USER}" ] ; then
        if [ -t 0 ] ; then
            read -r -p "Username: " CRYPTERA_ID_USER
        else
            err "CRYPTERA_ID_USER not set in environment and not running interactively"
        fi
    fi
    if [ -z "${CRYPTERA_ID_PASSWD}" ] ; then
        if [ -t 0 ] ; then
            read -r -s -p "Password: " CRYPTERA_ID_PASSWD
            echo ""
        else
            err "CRYPTERA_ID_PASSWD not set in environment and not running interactively"
        fi
    fi
    auth="$(printf "%s:%s" "${CRYPTERA_ID_USER}" "${CRYPTERA_ID_PASSWD}" | base64)"

    curl POST "${CRYPTERA_AUTHSERVER}/oauth2/token" \
         --header "Authorization: Basic ${auth}" \
         --data "grant_type=client_credentials" > "${tmpd}/token.json"

    CRYPTERA_ID_TOKEN=$(jq -r .access_token < "${tmpd}/token.json")
fi

mkdir -p "${output_dir}"

if [ $# -eq 0 ] ; then
    echo "Fetching all available public keys"

    curl GET "${CRYPTERA_KEYSERVER}/api/keys" --header "Authorization: Bearer ${CRYPTERA_ID_TOKEN}" > "${tmpd}/all-keys.json"

    jq -r '.[] | .keyid' < "${tmpd}/all-keys.json" | while read -r keyid ; do
        keyinfo=$(jq -r ".[] | select(.keyid == \"${keyid}\").keyinfo" < "${tmpd}/all-keys.json")
        echo "Writing certificate for $keyid ($keyinfo) to $keyid.pem"
        jq -j -r ".[] | select(.keyid == \"${keyid}\").certificate"  < "${tmpd}/all-keys.json" > "${output_dir}/${keyid}.pem"
    done
else
    for keyid ; do
        echo "Fetching information for ${keyid}"
        curl GET "${CRYPTERA_KEYSERVER}/api/keys/${keyid}" --header "Authorization: Bearer ${CRYPTERA_ID_TOKEN}" > "${tmpd}/${keyid}.json"
        keyinfo=$(jq -r ".keyinfo" < "${tmpd}/${keyid}.json")
        echo "Writing certificate for $keyid ($keyinfo) to $keyid.pem"
        jq -j -r ".certificate" < "${tmpd}/${keyid}.json" > "${output_dir}/${keyid}.pem"
    done
fi
