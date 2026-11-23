# Build plan

Status: steps 1–8 done (2026-11-23), tested live against Motive 3.1.0.1.

Each step ends with something testable. Steps marked **(live)** need this
machine on the MRS network with Motive streaming.

1. ~~**Repo skeleton**~~ ✅
   - `git init`, `pyproject.toml`, `.gitignore`, LICENSE (MIT), ruff, pytest.
2. ~~**Network scripts**~~ ✅
   - `setup/setup_network.sh` and `setup/check_network.sh`.
   - Test them on this machine. **(live)**
   - Both tested live on the maintainer's 26.04 laptop (wired), with ufw off
     and on. Confirmed: ufw on without the rule blocks the multicast data
     while the command port still answers (check: step 4 OK, step 5 FAIL);
     the rule from `setup_network.sh` fixes it.
3. ~~**Packet capture for tests**~~ ✅
   - Record a few real NatNet frames plus the model-definition reply to
     `tests/fixtures/`. **(live)**
   - These let the parser be tested offline and in CI.
4. ~~**Core receiver `optitrack_natnet/`**~~ ✅
   - Decided: own minimal parser (~150 lines, NatNet 4.1+, rigid bodies only),
     not the vendored SDK sample (Apache-2.0, 1,800 lines). 4.1's per-section
     byte counts let it skip everything else.
   - Write unit tests using the fixtures; then run a live test. **(live)**
5. ~~**Examples**~~ ✅
   - `print_poses.py` and `log_csv.py`.
6. ~~**ROS 2 package `optitrack_ros2`**~~ ✅
   - `PoseStamped` per rigid body plus TF.
   - Parameters: server IP, frame id, topic prefix.
   - Build and run on Lyrical here; check on a Humble lab machine.
   - Done: tested live on Lyrical (host) and Humble (lab Docker image,
     `--net=host`): 180 Hz pose + TF, `rate` limit, untracked-body warning.
   - Gotchas found: create_publisher() from the NatNet thread deadlocks
     (publishers are made on the ROS thread); untracked bodies publish
     nothing (node logs it); Lyrical removed logger.warn(); Ctrl+C on
     Lyrical raises RCLError from spin().
   - Still to test: a subscriber on another machine (ROS 2 + ufw).
7. ~~**Wi‑Fi**~~ ✅ (decided: optimise for cable; Wi‑Fi for checks only)
   - Measured live on the lab Wi‑Fi: power saving was the main cause of loss
     (35% → 76–99% of frames); `setup_network.sh` now turns it off.
   - Unicast measured at 100%; client supports it, lab stays on multicast.
   - Not built (not needed now): unicast relay, ROS 2-over-Wi‑Fi section.
8. ~~**README guide**~~ ✅
   - Follow the order in CLAUDE.md.
   - The troubleshooting table includes the Z-up check, and
     "Motive answers but no frames → firewall" (verified on 26.04).
9. **CI**
   - GitHub Actions: lint, unit tests on Python 3.8–3.14, and ROS 2 builds
     in Humble and Lyrical containers.
10. **Publish**
    - Home: github.com/ayalon-mrslab/optitrack-ubuntu (private; first pushed
      to AyalonLevy by mistake, transferred by the maintainer).
    - Later: transfer to `MRSTechnion`, then update the clone URLs in README.md
      (GitHub redirects the old URL, but the README should show the new one).
