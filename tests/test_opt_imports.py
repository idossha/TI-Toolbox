"""Lightweight mask/config imports must not initialize search engines."""

import subprocess
import sys


def test_mask_import_does_not_load_search_runners():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import tit.opt.masks; "
            "assert not any(n in sys.modules for n in "
            "('tit.opt.ex.ex', 'tit.opt.flex.flex', 'tit.opt.mex.mex')); "
            "from tit.opt import FlexConfig; assert FlexConfig.__name__ == 'FlexConfig'",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_public_runner_exports_remain_available():
    import tit.opt as opt
    from tit.opt.ex.ex import run_ex_search
    from tit.opt.flex.flex import run_flex_search
    from tit.opt.mex.mex import run_m_ex_search

    assert opt.run_ex_search is run_ex_search
    assert opt.run_flex_search is run_flex_search
    assert opt.run_m_ex_search is run_m_ex_search
