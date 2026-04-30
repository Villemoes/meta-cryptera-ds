import bb
import glob
import json
import os
import requests
import shlex
import time

def private_umask(func):
    def inner(*args, **kwargs):
        with bb.utils.umask(0o077):
            func(*args, **kwargs)
    return inner

# Simple wrapper for requests.request, handling some common things
# like automatically adding appropriate Accept: and/or Authorization:
# headers.
def request(method, url, id_token=None, expect_json=True, **kwargs):
    if id_token is not None or expect_json:
        headers = kwargs.get("headers", {}).copy()
        if expect_json:
            headers["Accept"] = "application/json"
        if id_token is not None:
            headers["Authorization"] = f"Bearer {id_token}"
        kwargs["headers"] = headers
    resp = requests.request(method, url, **kwargs)
    return resp

# Verify the response is as we expected. In order to be able to debug problems, be pretty verbose when something fails.
def check_response(resp, what, expected_status=200):
    if isinstance(expected_status, int):
        expected_status = [expected_status]
    if resp.status_code not in expected_status:
        msg = f"{what} failed: HTTP status {resp.status_code}, expected one of {expected_status}\n"
        msg += f"Request: {resp.request.method} {resp.request.url}\n"
        msg += f"Request headers: {resp.request.headers}\n"
        msg += f"Request body: {resp.request.body}\n"
        msg += f"Response headers: {resp.headers}\n"
        msg += f"Response body: {resp.text}\n"
        bb.fatal(msg)
    return None

def emit_env_files(d, env):
    with open(d.getVar("CRYPTERA_PIPELINE_ENV_SH"), "w") as f:
        for k,v in env.items():
            print("export %s=%s" % (k, shlex.quote(v)), file=f)

    with open(d.getVar("CRYPTERA_PIPELINE_ENV_JSON"), "w") as f:
        print(json.dumps(env, sort_keys=True, indent=4), file=f)

def emit_approval_file(d, reason):
    with open(d.getVar("CRYPTERA_PIPELINE_APPROVED"), "a") as f:
        print(reason, file=f)

def write_details_file(d, name, details):
    cpdir = d.getVar("CRYPTERA_PIPELINE_DIR")
    detailsdir = os.path.join(cpdir, "details")

    bb.utils.mkdirhier(detailsdir)
    try:
        with open(os.path.join(detailsdir, name + ".json"), "x") as f:
            print(json.dumps(details, sort_keys=True, indent=4), file=f)
    except FileExistsError:
        pass

def get_details(d, expected_status=200):
    with open(d.getVar("CRYPTERA_PIPELINE_ENV_JSON")) as f:
        env = json.load(f)

    server = env["KSC_API_SERVER"]
    operation_id = env["KSC_OPERATION_ID"]
    id_token = env["KSC_ID_TOKEN"]

    url = f"{server}/api/operations/{operation_id}"

    resp = request('GET', url, id_token)
    check_response(resp, "Checking pipeline details", expected_status=expected_status)

    return resp.json()

def check_approval(d):
    if os.path.exists(d.getVar("CRYPTERA_PIPELINE_APPROVED")):
        return True

    details = get_details(d)
    if details.get("approved"):
        write_details_file(d, "approved", details)
        return True
    else:
        return False

def collect_key_usage(cpdir, tasks):
    # key_usage is what keeps the key -> usage count.
    key_usage = {}

    # task_keys is the union of the of task -> key -> usage count maps
    # from each recipe, restricted to the tasks that will/may actually
    # run, mostly for information/debug purposes.
    task_keys = {}

    pndir = os.path.join(cpdir, "pn")
    for fn in glob.glob(os.path.join(pndir, "*.json")):
        with open(fn) as f:
            pntk = json.load(f)
        for t in pntk:
            if t not in tasks:
                continue
            tk = pntk[t]
            task_keys[t] = tk
            for kid in tk:
                if kid not in key_usage:
                    key_usage[kid] = tk[kid]
                else:
                    key_usage[kid] += tk[kid]

    return key_usage, task_keys

# prepare(evt, d): Called from global context, before individual
# recipes are parsed. Creates up a clean directory for collecting
# various info from recipes.

@private_umask
def prepare(evt, d):
    cpdir = d.getVar("CRYPTERA_PIPELINE_DIR")

    assert isinstance(evt, bb.event.ParseStarted)

    bb.note("Wiping directory '%s'" % cpdir)
    bb.utils.remove(cpdir, True)
    bb.utils.mkdirhier(cpdir)

# setup(evt, d): Called from global context, after all
# recipes have been parsed and all dependencies worked out.
#
# At that point, we know exactly which tasks are (or may be) run as
# part of the current build - some tasks may not need to run because
# they are already done. But the main point is that if somebody just
# said "bitbake util-linux", we won't have "kernel-fit.do_compile" in
# the list of tasks, and hence we can ignore any keys that would be
# required to sign kernel FIT images.
#
# This is not quite perfect, because if kernel.fit.do_compile is in
# the initial set of tasks, but doesn't actually have to run (and
# won't be, if bitbake sees there's no reason to), we'll still request
# those keys as part of the pipeline.

@private_umask
def setup(evt, d):
    cpdir = d.getVar("CRYPTERA_PIPELINE_DIR")

    assert isinstance(evt, bb.event.DepTreeGenerated)

    tasks_to_run = set(evt._depgraph["tdepends"].keys())

    key_usage, task_keys = collect_key_usage(cpdir, tasks_to_run)

    if not len(key_usage):
        # No keys stored on the key server required for any of the
        # tasks we're about to do, so no need to set up an "empty
        # pipeline".
        bb.plain("No Cryptera pipeline required for this build")

        # Create the approval file so the "wait for approval" steps become no-ops.
        emit_approval_file(d, "No pipeline, no approval required")

        # Emit dummy empty env files so any logic reading those files
        # can just do that unconditionally. The actual keys the
        # signing step(s) use are stored in local files, so there's no
        # information missing.
        emit_env_files(d, {})
        return

    # Don't force the user to bother with BB_ENV_PASSTHROUGH or
    # whatnot; we don't really want this stuff exposed to all tasks
    # anyway.
    origenv = d.getVar("BB_ORIGENV")

    # If we already have a KSC_ID_TOKEN (e.g. passed via the
    # environment), use that. Otherwise, assume we can obtain a token
    # via KSC_ID_USER/KSC_ID_PASSWORD
    id_token = origenv.getVar("KSC_ID_TOKEN") or ''
    if not id_token:
        id_user = origenv.getVar("KSC_ID_USER") or ''
        id_passwd = origenv.getVar("KSC_ID_PASSWD") or ''
        if not id_user or not id_passwd:
            bb.fatal("Neither KSC_ID_TOKEN or KSC_ID_USER/KSC_ID_PASSWD present in environment")
        url = d.getVar("CRYPTERA_AUTHSERVER") + "/oauth2/token"

        resp = request('POST', url, auth=(id_user, id_passwd), data={"grant_type": "client_credentials"})
        check_response(resp, "Authentication")

        id_token = resp.json()["access_token"]

    req = {
        "validms": int(d.getVar("CRYPTERA_PIPELINE_VALID_SECS") or "3600") * 1000,
        "description": d.getVar("CRYPTERA_PIPELINE_DESCRIPTION"),
        "new-keyusagerestrictions": [ { "keyid": k, "maxusagecount": v} for (k,v) in key_usage.items()]
    }
    url = d.getVar("CRYPTERA_KEYSERVER") + "/api/operations"

    resp = request('POST', url, id_token, json=req)
    check_response(resp, "Creating pipeline", expected_status=201)

    operation_id = resp.json()["id"]

    env = {
        "KSC_OPERATION_DESCRIPTION": d.getVar("CRYPTERA_PIPELINE_DESCRIPTION"),
        "KSC_API_SERVER":            d.getVar("CRYPTERA_KEYSERVER"),
        "KSC_OPERATION_ID":          operation_id,
        "KSC_ID_TOKEN":              id_token,
    }
    emit_env_files(d, env)

    details = get_details(d)
    write_details_file(d, "initial", details)

    if details.get("approved"):
        bb.note("Pipeline %s created, none of the keys required approval" % operation_id)
        emit_approval_file(d, "None of the keys required approval")
        return

    bb.note("Pipeline %s created, awaiting approval" % operation_id)

    # TODO? Here we might want to insert some "approve via the API"
    # call, perhaps guarded by some CRYPTERA_PIPELINE_SELF_APPROVE
    # variable (or we could just try unconditionally and ignore an
    # error?); then check the status again to see if it is now
    # "sufficiently" approved.

    # TODO? Add an option to wait for approval before proceeding to do
    # any building. It's simply a matter of adding a (conditional)
    # call to wait_for_approval() here.

# Split the string at whitespace, ignore any words starting with /
# (representing absolute paths to files), return a list of the
# remaining words with any "pkcs11:object=" prefix removed.
#
# This allows maximal flexibility in how one refers to the keys to use
# for signing, and one should in most cases be able to just put
# FOO_SIGNING_KEY into the do_bar[cryptera-keys] variable.
def filter_server_key_ids(s):
    kids = []
    for k in s.split():
        if k.startswith("/"):
            bb.debug(1, "Ignoring key identifier '%s'" % k)
            continue
        if k.startswith("pkcs11:object="):
            kids.append(k[14:])
        else:
            kids.append(k)
    return kids

# emit_key_usage(d): Hook called after the recipe metadata is
# completely finalized, via the bb.event.RecipeParsed event.
#
# This function is responsible for gathering the data on which keys
# the recipe needs (and how many times), and stashing that in a place
# where later logic can collect that data from the various recipes,
# and setup a pipeline request.
#
# The recipe is responsible for declaring which task(s) will actually
# perform signing, by setting the `CRYPTERA_SIGNING_TASKS`
# variable. In addition, each such task, say `do_compile`, must
# declare which key(s) it will make use of, via the `[cryptera-keys]`
# flag.
#
# We only care about entries that start with "pkcs11:object=", and
# then pick out the keyid after the equal sign. This makes it easier
# for a recipe to do something like
#
#   do_compile[cryptera-keys] = "${KERNEL_SIGNING_KEY}"
#
# and then for example have a way to set KERNEL_SIGNING_KEY to some
# path to a file containing a development key. In that case, we don't
# need to request a pipeline at all, so it's fine to just ignore such
# entries.
#
# There are two ways a recipe can indicate that a key is needed
# multiple times: The recipe can set `CRYPTERA_KEY_USAGE_COUNT` to
# some value other than 1. And/or it can have the same keyid appear
# multiple times. Every occurrence of a keyid results in a request of
# `CRYPTERA_KEY_USAGE_COUNT` uses of that key.
#
# This is to allow maximal flexibility. For example, if a kernel-fit
# recipe knows that it will always produce two FIT images, always
# signed with the same key, it's natural to have
#
#   do_compile[cryptera-keys] = "${KERNEL_SIGNING_KEY}"
#   CRYPTERA_KEY_USAGE_COUNT = "2"
#
# but if the keys are (or may be) different, it's more convenient to
# write
#
#   do_compile[cryptera-keys] = "${KERNEL_SIGNING_KEY} ${KERNEL_BOOTSTRAP_SIGNING_KEY}"
#
# (leaving `CRYPTERA_KEY_USAGE_COUNT` at its default value of 1).
#

def emit_key_usage(evt, d):
    assert isinstance(evt, bb.event.RecipeParsed)

    cpdir = d.getVar("CRYPTERA_PIPELINE_DIR")
    tasks = (d.getVar("CRYPTERA_SIGNING_TASKS") or "").split()
    count = int(d.getVar("CRYPTERA_KEY_USAGE_COUNT") or "1")
    pn = d.getVar("PN")

    # Mapping of $pn.$task -> { keyid -> usage count }
    task_keys = {}

    for t in tasks:
        tk = {}
        keys = (d.getVarFlag(t, "cryptera-keys") or "")
        for kid in filter_server_key_ids(keys):
            if kid not in tk:
                tk[kid] = count
            else:
                tk[kid] += count
        if len(tk):
            task_keys[pn + "." + t] = tk

    pndir = os.path.join(cpdir, "pn")
    bb.utils.mkdirhier(pndir)
    fn = os.path.join(pndir, pn + ".json")
    with open(fn, "w") as f:
        print(json.dumps(task_keys, sort_keys = True, indent = 4), file=f)

# wait_for_approval(d, timeout, interval): Wait for the pipeline to be
# approved. Guaranteed to succeed if the setup routine determined that
# no approval was necessary, or if some other task has already
# successfully polled for approval.
#
# Leave a little bread-crumbs in the approval file for debugging.
def wait_for_approval(d, timeout=None, interval=None):
    if timeout is None:
        timeout = int(d.getVar("CRYPTERA_APPROVAL_TIMEOUT") or "3600")
    if interval is None:
        interval = int(d.getVar("CRYPTERA_APPROVAL_POLL_INTERVAL") or "15")

    if d.getVar("BB_WORKERCONTEXT"):
        who = "%s:do_%s" % (d.getVar("PN"), d.getVar("BB_CURRENTTASK"))
    else:
        who = "global"

    printed = False

    start = time.time()
    while time.time() - start < timeout:
        if check_approval(d):
            emit_approval_file(d, "%s: pipeline approved after %.1f seconds" % (who, time.time()-start))
            return True
        if not printed:
            bb.verbnote("Waiting for pipeline approval, timeout is %d seconds" % timeout)
            printed = True
        time.sleep(interval)

    bb.fatal("Pipeline not approved within %d seconds" % timeout)

def shutdown(evt, d):
    assert isinstance(evt, bb.event.BuildCompleted)

    with open(d.getVar("CRYPTERA_PIPELINE_ENV_JSON")) as f:
        env = json.load(f)

    if "KSC_OPERATION_ID" not in env:
        # No pipeline created.
        return

    details = get_details(d)
    write_details_file(d, "final", details)

    server = env["KSC_API_SERVER"]
    operation_id = env["KSC_OPERATION_ID"]
    id_token = env["KSC_ID_TOKEN"]

    url = f"{server}/api/operations/{operation_id}"

    resp = request('DELETE', url, id_token)
    if resp.status_code == 200:
        details = get_details(d, expected_status = [200, 410])
        write_details_file(d, "cancelled", details)
    else:
        bb.verbnote("Unable to cancel pipeline")
