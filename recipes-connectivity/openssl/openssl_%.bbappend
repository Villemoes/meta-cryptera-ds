do_install:append:class-native () {
       mv ${D}${bindir}/openssl.real ${D}${bindir}/openssl
       create_wrapper ${D}${bindir}/openssl \
           OPENSSL_CONF=\${OPENSSL_CONF:-${libdir}/ssl-3/openssl.cnf} \
           SSL_CERT_DIR=\${SSL_CERT_DIR:-${libdir}/ssl-3/certs} \
           SSL_CERT_FILE=\${SSL_CERT_FILE:-${libdir}/ssl-3/cert.pem} \
           OPENSSL_ENGINES=\${OPENSSL_ENGINES:-${libdir}/engines-3} \
           OPENSSL_MODULES=\${OPENSSL_MODULES:-${libdir}/ossl-modules}
}
