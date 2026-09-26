# Local comparison image only, NOT a claim of official x86 runner parity.
# Native ARM browser + the pinned upstream x86 Octos executable via Docker's
# existing binfmt emulator. Keep native Python/Node identical for A and B.
FROM --platform=linux/amd64 arcbench-local-current:20260924 AS x86libs
FROM arcbench-local-legacy:20260924
COPY --from=x86libs /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/libgcc_s.so.1
COPY --from=x86libs /lib/x86_64-linux-gnu/libm.so.6 /lib/x86_64-linux-gnu/libm.so.6
COPY --from=x86libs /lib/x86_64-linux-gnu/libc.so.6 /lib/x86_64-linux-gnu/libc.so.6
COPY --from=x86libs /lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2
ENV PYTHONDONTWRITEBYTECODE=1
RUN python -m pip install --no-cache-dir arcbench-runtime==0.1.0
