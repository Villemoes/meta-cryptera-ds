# Use host certificates for non-target builds. As libcurl doesn't honor any of the env vars (like
# for example CURL_CA_PATH) that curl-cli does, we need to explicitly set '--with-ca-bundle'
# accordingly, so that there is a working, built-in default even for those tools that use libcurl,
# but don't have custom env var handling implemented (like opkg).
CURL_CA_BUNDLE_BASE_DIR ?= "/etc"
CURL_CA_BUNDLE_BASE_DIR:class-target = "${sysconfdir}"

EXTRA_OECONF:append = " \
    --with-ca-bundle=${CURL_CA_BUNDLE_BASE_DIR}/ssl/certs/ca-certificates.crt \
"
