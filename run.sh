#!/bin/bash
          case "test" in
                prereq_missing:ghaw_readiness:missing_*)
                  echo "::notice::FIX: the required file referenced in reason code is missing from the repository. Add it before merging." ;;
                prereq_missing:ghaw_readiness:missing_commit_sha)
                  echo "::notice::FIX: GITHUB_SHA is not set. This check requires a push or pull_request event context." ;;
                reject:path_filter:outside_raw_inbox:*)
                  echo "::notice::FIX: changed paths must be under raw/inbox/ only. Move files outside that directory to a separate commit." ;;
                prereq_missing:concurrency_guard:*)
                  echo "::notice::FIX: the concurrency block is missing or misconfigured. Ensure group and cancel-in-progress match the expected values." ;;
          esac
