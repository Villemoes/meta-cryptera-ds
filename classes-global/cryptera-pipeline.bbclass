# This class must be inherited globally via
#
#   INHERIT += "cryptera-pipeline"
#
# in a global configuration file in order to work.

include conf/cryptera.conf

### The variables below should/must be defined in a global
### configuration file such as local.conf, site.conf or
### ${MACHINE}.conf, or in a dedicated cryptera.conf.

CRYPTERA_PIPELINE_DESCRIPTION ??= "Firmware build for ${MACHINE}"

# Ideally, it should suffice to set CRYPTERA_SERVER_BASE. The port
# suffix variables should either be left empty or include a leading
# colon (":1234"), but in that case it may be just as simple to
# provide explicit definition for CRYPTERA_{AUTH,KEY}SERVER.
CRYPTERA_SERVER_BASE            ??= "this-must-be-provided.example.org"
CRYPTERA_AUTHSERVER_PORT_SUFFIX ??= ""
CRYPTERA_KEYSERVER_PORT_SUFFIX  ??= ""

CRYPTERA_AUTHSERVER    ??= "https://authserver.${CRYPTERA_SERVER_BASE}${CRYPTERA_AUTHSERVER_PORT_SUFFIX}"
CRYPTERA_KEYSERVER     ??= "https://keyserver.${CRYPTERA_SERVER_BASE}${CRYPTERA_KEYSERVER_PORT_SUFFIX}"


### Everything below this, including all variable definitions, should
### be considered internal implementation details, and you should not
### change anything unless you have a very good reason.

# The base directory where metadata related to the signing pipeline is
# stored. This directory is completely removed at the beginning of
# every build.
CRYPTERA_PIPELINE_DIR ??= "${TMPDIR}/cryptera"

# The pipeline setup will end up emitting two files with the
# information needed by the signing step, one for sourcing from a
# shell script, another with the same data in json format for reading
# from Python or some other language.
CRYPTERA_PIPELINE_ENV_SH   = "${CRYPTERA_PIPELINE_DIR}/pipeline-env.sh"
CRYPTERA_PIPELINE_ENV_JSON = "${CRYPTERA_PIPELINE_DIR}/pipeline-env.json"

# The tasks doing the signing must wait for the pipeline to be
# approved.
#
# Once any task determines that the pipeline is approved, or if no
# approval is needed (in particular, if no pipeline was _actually_ set
# up because no pkcs11: URIs were in use), this file is generated as
# an indication that the task may proceed to the actual signing.
CRYPTERA_PIPELINE_APPROVED = "${CRYPTERA_PIPELINE_DIR}/pipeline-approved.txt"

addhandler cryptera_prepare_pipeline
cryptera_prepare_pipeline[eventmask] = "bb.event.ParseStarted"
python cryptera_prepare_pipeline() {
    cryptera.pipeline.prepare(e, d)
}

addhandler cryptera_setup_pipeline
cryptera_setup_pipeline[eventmask] = "bb.event.DepTreeGenerated"
python cryptera_setup_pipeline() {
    cryptera.pipeline.setup(e, d)
}

addhandler cryptera_shutdown_pipeline
cryptera_shutdown_pipeline[eventmask] = "bb.event.BuildCompleted"
python cryptera_shutdown_pipeline() {
    cryptera.pipeline.shutdown(e, d)
}
