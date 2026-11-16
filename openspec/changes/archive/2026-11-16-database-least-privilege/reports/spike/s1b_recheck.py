from common import *
for db in ("postgres", "template1", "spk_other"):
    for who in ("app", "worker", "mig"):
        expect_error(who, db, "select 1", "A-09r", f"{USERS[who]} connect to {db}", "42501")
