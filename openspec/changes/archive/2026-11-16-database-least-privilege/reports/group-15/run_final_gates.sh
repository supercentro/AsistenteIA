#!/usr/bin/env bash
# Final gates of task 15.2 on a disposable PostgreSQL (one cluster per stage, see run_linux_tests.sh).
cd "$(dirname "$0")/../../../../.." || exit 1
R=openspec/changes/database-least-privilege/reports/group-15
bash $R/run_linux_tests.sh $R/final-1-unit.txt tests/unit
bash $R/run_linux_tests.sh $R/final-2-integration-ordinary.txt -m "not role_bound and not realmodel" tests/integration
bash $R/run_linux_tests.sh $R/final-3-role-bound.txt -m role_bound tests/integration
bash $R/run_linux_tests.sh $R/final-4-roles-mode.txt --least-privilege -m least_privilege tests/integration
