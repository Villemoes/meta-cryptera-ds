SUMMARY = "Shared library exposing a pkcs#11 interface to Cryptera's key servers"

LICENSE = "Proprietary"
LIC_FILES_CHKSUM = "file://src/${GO_IMPORT}/LICENSE.md;md5=f30fb6c072a73bf2916acf24ecfcd9a6"

GO_IMPORT = "github.com/cryptera-device-security/libpkcs11ks"

# Remove this when dropping scarthgap support.
GO_SRCURI_DESTSUFFIX ??= "${@os.path.join(os.path.basename(d.getVar('S')), 'src', d.getVar('GO_IMPORT')) + '/'}"

SRC_URI = "git://${GO_IMPORT};name=ks;protocol=https;branch=main;destsuffix=${GO_SRCURI_DESTSUFFIX}"
SRCREV_ks        = "6609bfa6999ba1426aae0901aa9d88b9b27b6d8d"

#       github.com/namecoin/pkcs11mod v[something not officially tagged...]
SRC_URI += "git://github.com/namecoin/pkcs11mod;protocol=https;name=pkcs11mod;branch=master;destsuffix=vendor/src/github.com/namecoin/pkcs11mod"
SRCREV_pkcs11mod = "8389aedc2a5fdcd871f23dc40a8816e65368d92f"

#       github.com/miekg/pkcs11 v1.1.1
SRC_URI += "git://github.com/miekg/pkcs11;name=pkcs11;protocol=https;nobranch=1;destsuffix=vendor/src/github.com/miekg/pkcs11"
SRCREV_pkcs11    = "f3481918a208bd212aa995a41f92d786eb418a7d"

#       golang.org/x/crypto v0.28.0
SRC_URI += "git://go.googlesource.com/crypto;name=crypto;protocol=https;nobranch=1;destsuffix=vendor/src/golang.org/x/crypto"
SRCREV_crypto    = "adef4cc1a8c2ca4da1b1f4e6c976b59ca22dbfb8"

# This is annoying. The pkcs11mod repo does not contain a go.mod or
# go.sum file. It contains instructions to generate those on-the-fly
# with "go mod init". But that doesn't work in bitbake context: First,
# it means we haven't pinned the dependencies completely. Second, it
# requires network access.
#
# So those files have been stashed and included them with this recipe.
SRC_URI += "file://github.com/namecoin/pkcs11mod/go.mod;subdir=vendor/src"
SRC_URI += "file://github.com/namecoin/pkcs11mod/go.sum;subdir=vendor/src"

SRCREV_FORMAT = "ks_pkcs11mod_pkcs11_crypto"

inherit go

export GO111MODULE = "off"

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
    cd "${UNPACKDIR}/vendor/src/github.com/namecoin/pkcs11mod"
    go generate ./...
    )

    export GOPATH="${GOPATH}:${WORKDIR}/build/vendor/"
    export TMPDIR="${GOTMPDIR}"

    ${GO} build ${GOBUILDFLAGS} -buildmode=c-shared -o libpkcs11keyserver.so "${GO_IMPORT}"
}

do_install:append() {
    install -d "${D}${libdir}/pkcs11"
    install -m 0755 libpkcs11keyserver.so "${D}${libdir}/pkcs11"
}

FILES:${PN} += "${libdir}"

RDEPENDS:${PN} += "libp11"
RDEPENDS:${PN} += "openssl"

# TODO? Allow building a nativesdk- variant?
BBCLASSEXTEND = "native"
