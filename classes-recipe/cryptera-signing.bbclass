# This class must be inherited by each recipe that needs to perform
# signing using the Cryptera key server.

# Do _not_ inherit it globally via the INHERIT variable.

include conf/cryptera.conf

CRYPTERA_SIGNING_TASKS ??= "do_compile"
CRYPTERA_KEY_USAGE_COUNT ??= "1"

DEPENDS += "cryptera-libpkcs11ks-native"
DEPENDS += "openssl-native"
DEPENDS += "ca-certificates-native"

CRYPTERA_OPENSSL_CONF = "${STAGING_ETCDIR_NATIVE}/cryptera/engine.conf"

python() {
    # The setup/request of a pipeline requires that the
    # cryptera-pipeline class is inherited globally. It cannot be
    # inherited just by individual recipes (and thus it makes no sense
    # to add an inherit statement in this class). Do not make it a
    # fatal error at parse time; but if such a recipe must be built
    # either explicitly or via some dependency, bitbake will print
    # this message explaining why the recipe was skipped.
    if not bb.data.inherits_class("cryptera-pipeline", d):
        msg = "Use of cryptera-signing.bbclass requires cryptera-pipeline.bbclass being inherited globally ('INHERIT += \"cryptera-pipeline\"')"
        raise bb.parse.SkipRecipe(msg)

    # We depend on a side effect of recipe parsing emitting certain
    # metadata about the keys that will be used to a shared location,
    # so that a Cryptera pipeline can be requested and approved. Thus,
    # we must force bitbake to go through the motions of parsing this
    # recipe every time - which is one reason this class should not be
    # inherited globally.
    d.setVar("BB_DONT_CACHE", "1")

    # Mark each task in CRYPTERA_SIGNING_TASKS as making use of
    # network.  Also, inject a prefunc to ensure that the "pipeline"
    # is approved before the signing takes place.
    #
    # One small caveat: You cannot do signing in a prefunc of the real
    # task function, at least not unless you take great care to ensure
    # that your prefunc runs after cryptera_wait_for_approval. In
    # practice, this really should not be an issue.
    #
    # [Ideally, we'd instead add a separate do_wait_for_approval task
    # ordered before the task doing the signing. However, we cannot do
    # that, as that task would either not run again when rebuilding
    # (because bitbake has already created an up-to-date stamp file),
    # or we make it a [nostamp] task, in which case _all_ dependent
    # tasks would always be "tainted" and always run. So we must allow
    # bitbake's usual logic for deciding whether, say, do_compile,
    # needs to be run, and then just inject the relevant piece of code
    # as part of that, which will then run *if and only if* do_compile
    # ends up being run. Using the [prefuncs] mechanism works just
    # fine for this, with that small caveat.]

    for t in d.getVar("CRYPTERA_SIGNING_TASKS").split():
        keys = d.getVarFlag(t, "cryptera-keys") or ""
        if cryptera.pipeline.filter_server_key_ids(keys):
            d.setVarFlag(t, "network", "1")
            prefuncs = (d.getVarFlag(t, "prefuncs") or "").split()
            prefuncs.insert(0, "cryptera_wait_for_approval")
            d.setVarFlag(t, "prefuncs", " ".join(prefuncs))
}

python cryptera_wait_for_approval() {
    cryptera.pipeline.wait_for_approval(d)
}

addhandler cryptera_emit_key_usage
cryptera_emit_key_usage[eventmask] = "bb.event.RecipeParsed"
python cryptera_emit_key_usage() {
    cryptera.pipeline.emit_key_usage(e, d)
}
