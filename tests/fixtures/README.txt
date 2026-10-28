ok.sta, failed.sta, running.sta, ok.msg, nobc.msg, cae_error.stderr: hand-written samples in the documented
Abaqus .sta/.msg layout (nobc.msg is an excerpt of a real run without BCs).
upsetting/: real Abaqus/Standard 2026 outputs (.sta, .msg, .dat) of the C7 upsetting run
(upsetting, initial increment 0.01) and of the same model with the initial increment equal to the
step time (upsetting-cutback, forces cut-backs), fetched by tests/test_e2e_upsetting.py.
