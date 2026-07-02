SUMMARY = "Shared library exposing a pkcs#11 interface to Cryptera's key servers"

LICENSE = "Cryptera"
LIC_FILES_CHKSUM = "file://src/${GO_IMPORT}/LICENSE.md;md5=f30fb6c072a73bf2916acf24ecfcd9a6"

GO_IMPORT = "github.com/cryptera-device-security/libpkcs11ks"

SRC_URI = "git://${GO_IMPORT};name=ks;protocol=https;branch=main;destsuffix=${GO_SRCURI_DESTSUFFIX}"
SRCREV_ks        = "950de36387690f1d3d5373c9ee70f07e8c12a692"

#       github.com/cryptera-device-security/pkcs11mod v1.0.1
SRC_URI += "git://github.com/cryptera-device-security/pkcs11mod;protocol=https;name=pkcs11mod;branch=master;destsuffix=vendor/src/github.com/cryptera-device-security/pkcs11mod"
SRCREV_pkcs11mod = "a0c56ed174ae4138b4b060a01029c5acdeea2750"

#       github.com/miekg/pkcs11 v1.1.1
SRC_URI += "git://github.com/miekg/pkcs11;name=pkcs11;protocol=https;nobranch=1;destsuffix=vendor/src/github.com/miekg/pkcs11"
SRCREV_pkcs11    = "f3481918a208bd212aa995a41f92d786eb418a7d"

#       golang.org/x/crypto v0.50.0
SRC_URI += "git://go.googlesource.com/crypto;name=crypto;protocol=https;nobranch=1;destsuffix=vendor/src/golang.org/x/crypto"
SRCREV_crypto    = "03ca0dcccbd37ba6be80adf74dde8d78a4d72817"

SRC_URI += "file://openssl.conf"

SRCREV_FORMAT = "ks_pkcs11mod_pkcs11_crypto"

inherit go

export GO111MODULE = "off"

PKCS11_ENGINE_PATH = "${libdir}/engines-3/pkcs11.so"
PKCS11_PROVIDER_PATH = "${libdir}/ossl-modules/pkcs11prov.so"
CRYPTERA_PKCS11_MODULE_PATH = "${libdir}/pkcs11/libpkcs11keyserver.so"

do_compile() {
    # arrange for some of the golang built ins to be found
    (
	cd ${WORKDIR}/build/src/
	ln -sf ${STAGING_DIR_TARGET}/${prefix}/lib/go/src/cmd/vendor/golang.org .

	cd ${WORKDIR}/build/
	ln -sf ${UNPACKDIR}/vendor .
    )

    (
    # Now we need to enter the pkcs11mod repo and do "go
    # generate". Its Makefile assumes GOPATH includes only a single
    # item, and we have to set it so that it ends up picking up the
    # header files from the miekg/pkcs11 module.
    export GOPATH="${WORKDIR}/build/vendor"
    cd "${UNPACKDIR}/vendor/src/github.com/cryptera-device-security/pkcs11mod"
    go generate ./...
    )

    export GOPATH="${GOPATH}:${WORKDIR}/build/vendor/"
    export TMPDIR="${GOTMPDIR}"

    ${GO} build ${GOBUILDFLAGS} -buildmode=c-shared -o libpkcs11keyserver.so "${GO_IMPORT}"
}

do_install:append() {
    install -d "${D}${libdir}/pkcs11"
    install -m 0755 libpkcs11keyserver.so "${D}${libdir}/pkcs11"
    install -d ${D}${sysconfdir}/cryptera
    install -m 0644 ${UNPACKDIR}/openssl.conf ${D}${sysconfdir}/cryptera/

    sed -i -e "s|@@PKCS11_ENGINE_PATH@@|${PKCS11_ENGINE_PATH}|" \
           -e "s|@@PKCS11_PROVIDER_PATH@@|${PKCS11_PROVIDER_PATH}|" \
           -e "s|@@CRYPTERA_PKCS11_MODULE_PATH@@|${CRYPTERA_PKCS11_MODULE_PATH}|" \
              ${D}${sysconfdir}/cryptera/openssl.conf
}

FILES:${PN} += "${libdir}"

RDEPENDS:${PN} += "libp11"
RDEPENDS:${PN} += "openssl"

# TODO? Allow building a nativesdk- variant?
BBCLASSEXTEND = "native"
