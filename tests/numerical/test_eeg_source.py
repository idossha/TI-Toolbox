"""Real-MNE EEG/source extraction contracts (2026-09-13).

Run: simnibs_python -m pytest tests/numerical/test_eeg_source.py -q
Set TIT_EEG_TEST_PYTHON to test a different installed MNE interpreter explicitly.
Numbers come from independently invoked public MNE APIs or analytic graph/time
invariants, never cached output of the wrappers. Each test uses a fresh Python
process so the host suite's module mocks cannot masquerade as numerical proof.
No datasets are downloaded. Real FEM/head-model parity is a separate data test.
"""

from pathlib import Path
import os
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_real(code: str) -> None:
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT),
        MNE_DONTWRITE_HOME="true",
        MNE_HOME="/tmp/mne-home",
        MPLBACKEND="Agg",
        TIT_NO_TELEMETRY="1",
    )
    python = os.environ.get("TIT_EEG_TEST_PYTHON", sys.executable)
    probe = subprocess.run(
        [python, "-c", "import mne, scipy, numpy"],
        env=env,
        capture_output=True,
        text=True,
    )
    if probe.returncode:
        pytest.skip(f"Real MNE/scipy unavailable in {python}: {probe.stderr}")
    result = subprocess.run(
        [python, "-c", textwrap.dedent(code)],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_noise_epochs_first_sample_exact_fit_and_exclusions():
    # Only this case catches the raw-relative/absolute offset and terminal-epoch bugs.
    run_real("""
        import mne
        import numpy as np
        from tit.source.reconstruction import epochs_from_intervals, subtract_intervals
        info = mne.create_info(['Cz'], 10, 'eeg')
        raw = mne.io.RawArray(np.arange(100)[None, :] * 1e-6, info, first_samp=50, verbose=False)
        epochs = epochs_from_intervals(raw, [(0, 10)], exclusions=[(2, 4)], epoch_duration=2)
        # Authored timeline: [0,2), [4,6), [6,8), [8,10), absolute starts +50.
        np.testing.assert_array_equal(epochs.events[:, 0], [50, 90, 110, 130])
        np.testing.assert_allclose(epochs.get_data()[:, 0, 0], np.array([0,40,60,80]) * 1e-6)
        assert subtract_intervals([(0, 10)], [(2,4), (3,5), (7,8)]) == [(0,2), (5,7), (8,10)]
        raw_zero = mne.io.RawArray(np.arange(100)[None, :] * 1e-6, info, verbose=False)
        old = epochs_from_intervals(raw_zero, [(0,10)], epoch_duration=2, legacy_sampling=True)
        np.testing.assert_array_equal(old.events[:, 0], [0,20,40,60])
    """)


def test_covariance_matches_independent_mne_epochs():
    run_real("""
        import mne
        import numpy as np
        from tit.source.reconstruction import covariance_from_intervals
        rng = np.random.default_rng(20)
        raw = mne.io.RawArray(rng.normal(size=(3, 600)) * 1e-6,
                             mne.create_info(['C3','Cz','C4'], 100, 'eeg'), verbose=False)
        expected_epochs = mne.Epochs(raw, np.array([[0,0,1],[200,0,1],[400,0,1]]),
                                    {'noise':1}, tmin=0, tmax=1.99, baseline=None, preload=True, verbose=False)
        expected = mne.compute_covariance(expected_epochs, method='empirical', rank=None, verbose=False)
        actual = covariance_from_intervals(raw, [(0,6)], method='empirical')
        np.testing.assert_allclose(actual.data, expected.data, rtol=1e-14, atol=0)
    """)


def test_harmonization_preserves_metadata_and_matches_mne_interpolation():
    run_real("""
        import mne
        import numpy as np
        from tit.eeg import harmonize_channels
        names = ['Fp1','Fp2','F3','F4','C3','C4','P3','P4','O1','O2']
        montage = mne.channels.make_standard_montage('standard_1020')
        raw = mne.io.RawArray(np.random.default_rng(8).normal(size=(len(names), 40)) * 1e-6,
                             mne.create_info(names, 100, 'eeg'), first_samp=200, verbose=False)
        raw.set_montage(montage)
        raw.set_annotations(mne.Annotations([0.1], [0.05], ['event']))
        raw.info['bads'] = ['C3']
        expected = raw.copy().interpolate_bads(reset_bads=True, verbose=False)
        actual = harmonize_channels(raw, names, montage)
        np.testing.assert_allclose(actual.get_data(), expected.get_data(), rtol=1e-14, atol=0)
        assert raw.info['bads'] == ['C3'] and actual.info['bads'] == []
        assert actual.first_samp == raw.first_samp
        np.testing.assert_array_equal(actual.annotations.onset, raw.annotations.onset)
        incomplete = raw.copy().drop_channels(['C4'])
        restored = harmonize_channels(incomplete, names, montage, preserve_bads=False)
        # Legacy mode interpolates newly missing C4 and retains existing C3 signal.
        np.testing.assert_array_equal(restored.get_data(picks=['C3']), raw.get_data(picks=['C3']))
        assert restored.ch_names == names and restored.first_samp == 200
    """)


def test_annotations_and_protocol_window_policies():
    run_real("""
        import mne
        import numpy as np
        from tit.eeg import annotation_pairs, stimulation_windows
        raw = mne.io.RawArray(np.zeros((1, 100)), mne.create_info(['Cz'], 10, 'eeg'),
                             first_samp=50, verbose=False)
        raw.set_annotations(mne.Annotations([1,3,6,8], [0]*4, ['STIM-start','stim end']*2))
        assert annotation_pairs(raw,'stim start','stim end') == [(1,3),(6,8)]
        assert annotation_pairs(raw,'stim start','stim end', relative_to_raw=False) == [(6,8),(11,13)]
        windows = stimulation_windows([(2,4),(6,8)])
        assert windows[0].post_end_sec == windows[1].pre_start_sec == 5
        assert (windows[0].pre_start_sec, windows[1].post_end_sec) == (0,10)
    """)


def test_graph_diffusion_matches_manual_neighbor_averaging():
    run_real("""
        import numpy as np
        from scipy.sparse import csr_matrix
        from tit.source.reconstruction import diffusion_smoother
        # Authored chain with one isolated vertex. Average each node with its neighbors.
        adjacency = csr_matrix([[0,1,0,0],[1,0,1,0],[0,1,0,0],[0,0,0,0]])
        matrix = diffusion_smoother(adjacency, 2)
        x = np.array([1.,4.,10.,9.])
        first = np.array([(1+4)/2, (1+4+10)/3, (4+10)/2, 9])
        expected = np.array([(first[0]+first[1])/2, first[:3].mean(), (first[1]+first[2])/2, 9])
        np.testing.assert_allclose(matrix @ x, expected, rtol=1e-14)
        np.testing.assert_allclose(matrix @ np.ones(4), np.ones(4), rtol=1e-14)
    """)


def test_sensor_adjacency_reordering_matches_public_mne():
    run_real("""
        import mne
        import numpy as np
        from tit.eeg import sensor_adjacency
        names=['F3','F4','C3','C4','P3','P4']
        info=mne.create_info(names,100,'eeg')
        info.set_montage('standard_1020')
        wanted=names[::-1]
        matrix, ordered, index=sensor_adjacency(info,wanted)
        expected_info=mne.pick_info(info,mne.pick_channels(names,wanted,ordered=True))
        expected, expected_names=mne.channels.find_ch_adjacency(expected_info,'eeg')
        assert ordered == expected_names
        assert [wanted[i] for i in index] == ordered
        np.testing.assert_array_equal(matrix.toarray(), expected.toarray())
    """)


def test_batched_inverse_matches_independent_mne_epochs():
    run_real("""
        import mne
        import numpy as np
        from tit.source.reconstruction import prepare_inverse, apply_inverse_windows
        names=['Fp1','Fp2','F3','F4','C3','C4','P3','P4','O1','O2']
        info=mne.create_info(names,100,'eeg'); info.set_montage('standard_1020')
        raw=mne.io.RawArray(np.random.default_rng(2).normal(size=(10,100))*1e-6,info,verbose=False)
        raw.set_eeg_reference(projection=True,verbose=False)
        sphere=mne.make_sphere_model(r0=(0,0,0),head_radius=0.09,verbose=False)
        # Discrete interior dipoles avoid a dataset or a FreeSurfer subject.
        source=mne.setup_volume_source_space(pos=dict(rr=np.array([[.01,.02,.03],[-.02,.01,.04]]),
                                            nn=np.array([[0,0,1],[0,1,0]])),verbose=False)
        forward=mne.make_forward_solution(raw.info,trans=None,src=source,bem=sphere,eeg=True,meg=False,verbose=False)
        covariance=mne.make_ad_hoc_cov(raw.info,verbose=False)
        inverse=prepare_inverse(raw.info,forward,covariance,loose=1.,depth=None)
        offsets=np.array([-2,0,2]); peaks=np.array([10,50,80])
        event_data=np.stack([raw.get_data()[:,peak+offsets] for peak in peaks])
        epochs=mne.EpochsArray(event_data,raw.info,baseline=None,verbose=False)
        for method in ('MNE','sLORETA'):
            for orientation in (None,'vector'):
                expected=mne.minimum_norm.apply_inverse_epochs(epochs,inverse,lambda2=1/9,
                         method=method,pick_ori=orientation,verbose=False)
                actual=apply_inverse_windows(raw.get_data(),raw.info,inverse,peaks,offsets,
                         lambda2=1/9,method=method,pick_ori=orientation)
                independent=np.stack([stc.data for stc in expected], axis=-2)
                # Same linear algebra reordered in batches: floating reduction roundoff only.
                np.testing.assert_allclose(actual,independent,rtol=1e-12,atol=1e-20)
    """)


def test_forward_recording_frame_and_explicit_transform():
    run_real("""
        import mne
        import numpy as np
        from tit.source.forward import _build_montage_info
        fids={'LPA':np.array([-.08,0,0]),'Nz':np.array([0,.10,0]),'RPA':np.array([.08,0,0])}
        electrodes={'Cz':np.array([0,0,.09]),'Fpz':np.array([0,.08,.04])}
        info=mne.create_info(['Cz','Fpz'],100,'eeg')
        info.set_montage(mne.channels.make_dig_montage(ch_pos=electrodes,lpa=fids['LPA'],
                         nasion=fids['Nz'],rpa=fids['RPA'],coord_frame='head'))
        translation=np.array([.01,-.02,.03])
        mri_fids={key:value+translation for key,value in fids.items()}
        mri_electrodes={key:value+translation for key,value in electrodes.items()}
        built, transform=_build_montage_info(mri_electrodes,mri_fids,info=info)
        # Authored rigid frame: same electrodes translated in MRI. No fit to wrapper output.
        np.testing.assert_allclose(transform['trans'][:3,3],translation,atol=1e-8)
        for channel in built['chs']:
            np.testing.assert_allclose(channel['loc'][:3],electrodes[channel['ch_name']],atol=1e-8)
        explicit=mne.transforms.Transform('head','mri',transform['trans'])
        rebuilt, reused=_build_montage_info(mri_electrodes,mri_fids,trans=explicit)
        np.testing.assert_array_equal(reused['trans'],explicit['trans'])
    """)


def test_external_study_baseline_primitive_parity():
    """Optional code-baseline comparison; no participant files are accessed."""
    study = os.environ.get("TIT_EEG_STUDY_ROOT")
    if not study:
        pytest.skip(
            "TIT_EEG_STUDY_ROOT unset: external v1.0-preliminary study code parity not requested"
        )
    run_real("""
        import ast
        import dataclasses
        import os
        from pathlib import Path
        import subprocess
        import mne
        import numpy as np
        import pandas as pd
        import scipy.sparse as sp
        from tit.eeg import harmonize_channels, annotation_pairs, stimulation_windows
        from tit.source.reconstruction import covariance_from_intervals, diffusion_smoother
        root=Path(os.environ['TIT_EEG_STUDY_ROOT'])
        def load_function(path,name,namespace):
            source=subprocess.check_output(['git','show',f'v1.0-preliminary:{path}'],cwd=root,text=True)
            node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
            future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
            module=ast.fix_missing_locations(ast.Module(body=[future,node],type_ignores=[]))
            exec(compile(module,path,'exec'),namespace)
            return namespace[name]
        source_path='src/source/source/density.py'
        namespace=dict(mne=mne,np=np,pd=pd,sp=sp)
        old_cov=load_function(source_path,'wave_free_noise_cov',namespace)
        old_smoother=load_function(source_path,'build_diffusion_smoother',namespace)
        raw=mne.io.RawArray(np.random.default_rng(91).normal(size=(4,2000))*1e-6,
                mne.create_info(['C3','Cz','C4','Pz'],100,'eeg'),verbose=False)
        from types import SimpleNamespace
        protocols=[SimpleNamespace(pre_start_sec=0.,pre_end_sec=20.)]
        waves=pd.DataFrame({'Start':[2.,2.5,12.],'End':[3.,4.,13.]})
        before=old_cov(raw,protocols,waves)
        after=covariance_from_intervals(raw,[(0,20)],exclusions=[(r.Start-.5,r.End+.5) for r in waves.itertuples()],
                                       legacy_sampling=True)
        np.testing.assert_allclose(after.data,before.data,rtol=1e-14,atol=0)
        graph=sp.csr_matrix([[0,1,0],[1,0,1],[0,1,0]])
        np.testing.assert_array_equal(diffusion_smoother(graph,5).toarray(),old_smoother(graph,5).toarray())
        # Evaluate the historical interpolation body against the same in-memory recording.
        names=['Fp1','Fp2','F3','F4','C3','C4','P3','P4','O1','O2']
        import logging
        old_io=load_function('src/shared/io.py','load_set',dict(mne=mne,np=np,Path=Path,
             logger=logging.getLogger('parity'),EXCLUDE_CHANNELS=[],N_WORKING_CHANNELS=len(names),
             working_channel_names=lambda:names))
        # Use the actual study montage/channel policy from the baseline, not the small example cap.
        channel_source=subprocess.check_output(['git','show','v1.0-preliminary:src/shared/channels.py'],cwd=root,text=True)
        channels={};exec(channel_source,channels)
        template=channels['working_channel_names']()
        old_io.__globals__.update(EXCLUDE_CHANNELS=channels['EXCLUDE_CHANNELS'],N_WORKING_CHANNELS=len(template),
                                  working_channel_names=lambda:template)
        raw=mne.io.RawArray(np.random.default_rng(9).normal(size=(len(template)-1,50))*1e-6,
                           mne.create_info(template[:-1],100,'eeg'),verbose=False)
        raw.info['bads']=[template[3]]
        reader=mne.io.read_raw_eeglab
        mne.io.read_raw_eeglab=lambda *a,**k:raw.copy()
        try:
            before=old_io(Path('synthetic.set'))
        finally:
            mne.io.read_raw_eeglab=reader
        after=harmonize_channels(raw,template,'GSN-HydroCel-256',exclude=channels['EXCLUDE_CHANNELS'],preserve_bads=False)
        np.testing.assert_allclose(after.get_data(),before.get_data(),rtol=1e-14,atol=0)
        assert after.ch_names == before.ch_names and after.info['bads'] == before.info['bads']
        # Build the old dataclass/module without importing the migrated implementation.
        import types, sys
        old_segments=types.ModuleType('baseline_segments');sys.modules[old_segments.__name__]=old_segments
        text=subprocess.check_output(['git','show','v1.0-preliminary:src/shared/segments.py'],cwd=root,text=True)
        exec(text,old_segments.__dict__)
        raw=mne.io.RawArray(np.zeros((1,2000)),mne.create_info(['Cz'],1,'eeg'),verbose=False)
        raw.set_annotations(mne.Annotations([300,480,650,830],[0]*4,['STIM-start','stim end']*2))
        old_pairs=old_segments.find_stim_pairs(raw)
        new_pairs=annotation_pairs(raw,'stim start','stim end',min_duration=170,max_duration=220,relative_to_raw=False)
        assert old_pairs == new_pairs
        assert [dataclasses.asdict(w) for w in old_segments.build_protocols(old_pairs)] == [dataclasses.asdict(w) for w in stimulation_windows(new_pairs)]
    """)


def test_external_study_baseline_origin_scoring_parity():
    """Same synthetic inverse/source signals through frozen and migrated scorers."""
    if not os.environ.get("TIT_EEG_STUDY_ROOT"):
        pytest.skip(
            "TIT_EEG_STUDY_ROOT unset: external v1.0-preliminary scoring parity not requested"
        )
    run_real("""
        import ast
        import os
        import subprocess
        import time
        from pathlib import Path
        from types import SimpleNamespace
        import mne
        import numpy as np
        import pandas as pd
        import scipy.sparse as sp
        from tit.source.reconstruction import prepare_inverse, apply_inverse_windows, diffusion_smoother
        root=Path(os.environ['TIT_EEG_STUDY_ROOT'])
        names=['Fp1','Fp2','F3','F4','C3','C4','P3','P4','O1','O2']
        raw=mne.io.RawArray(np.random.default_rng(2).normal(size=(10,1200))*1e-6,
                           mne.create_info(names,250,'eeg'),verbose=False)
        raw.set_montage('standard_1020');raw.set_eeg_reference(projection=True,verbose=False)
        sphere=mne.make_sphere_model(r0=(0,0,0),head_radius=0.09,verbose=False)
        src=mne.setup_volume_source_space(pos=dict(rr=np.array([[.01,.02,.03],[-.02,.01,.04]]),
                            nn=np.array([[0,0,1],[0,1,0]])),verbose=False)
        fwd=mne.make_forward_solution(raw.info,trans=None,src=src,bem=sphere,eeg=True,meg=False,verbose=False)
        inv=prepare_inverse(raw.info,fwd,mne.make_ad_hoc_cov(raw.info,verbose=False),loose=1.,depth=None)
        class SyntheticMorph:
            # Authored 2-vertex linear map, independent of cortical mapping implementation.
            vertices_to=[np.array([0]),np.array([1])]
            def apply(self, stc, verbose=False):
                out=stc.copy();out.data=np.array([[.8,.2],[.1,.9]])@stc.data
                return out
        morph=SyntheticMorph()
        waves=pd.DataFrame({'NegPeak':np.arange(100,1000,100)/250,
                            'seg':['pre']*3+['stim']*3+['post']*3})
        def setup(paths, depth=None):
            return raw.get_data(),raw.info,250.,waves,inv,morph,2
        old_text=subprocess.check_output(['git','show','v1.0-preliminary:src/source/source/origin.py'],cwd=root,text=True)
        new_text=(root/'src/source/source/origin.py').read_text()
        def scorer(text):
            tree=ast.parse(text)
            keep=[n for n in tree.body if isinstance(n,ast.Assign) or
                  isinstance(n,ast.FunctionDef) and n.name=='compute_subject']
            future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
            module=ast.fix_missing_locations(ast.Module(body=[future,*keep],type_ignores=[]))
            namespace=dict(time=time,Path=Path,np=np,mne=mne,setup_subject=setup,
                           CFG_INV=SimpleNamespace(lambda2=1/9,method='sLORETA',pick_ori=None),
                           build_diffusion_smoother=diffusion_smoother,
                           apply_inverse_windows=apply_inverse_windows)
            exec(compile(module,'origin.py','exec'),namespace)
            return namespace['compute_subject']
        # Geometry loading alone is replaced with an authored chain; no source data are mocked.
        mne.datasets.fetch_fsaverage=lambda **kwargs:'/unused/fsaverage'
        mne.read_source_spaces=lambda *args,**kwargs:None
        mne.spatial_src_adjacency=lambda *args,**kwargs:sp.csr_matrix([[0,1],[1,0]])
        old=scorer(old_text)(SimpleNamespace(subject_id='synthetic'))
        new=scorer(new_text)(SimpleNamespace(subject_id='synthetic'))
        assert old.keys()==new.keys()
        for key in old:
            if key in ('setup_sec','compute_sec'):
                continue
            if isinstance(old[key],np.ndarray):
                np.testing.assert_allclose(new[key],old[key],rtol=1e-14,atol=0,err_msg=key)
            else:
                assert new[key]==old[key],key
    """)


def test_explicit_transform_reassembles_cached_forward_without_rerunning_fem():
    # Filesystem/FEM process boundaries are replaced; MNE transform I/O remains real.
    run_real("""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import mne
        import numpy as np
        import tit.source.forward as forward
        from tit.source.config import ForwardConfig
        fids={'LPA':np.array([-.08,0,0]),'Nz':np.array([0,.10,0]),'RPA':np.array([.08,0,0])}
        electrodes={'Cz':np.array([0,0,.09]),'Fpz':np.array([0,.08,.04])}
        with TemporaryDirectory() as directory:
            directory=Path(directory);model=directory/'m2m';model.mkdir()
            output=directory/'forward';output.mkdir();leadfield=output/'cached.hdf5';leadfield.touch()
            expected=tuple(output/f'custom{suffix}' for suffix in ('-fwd.fif','-src.fif','-morph.h5'))
            for path in expected:path.touch()
            with patch.object(forward,'_check_forward_dependencies'), \
                 patch.object(forward,'_forward_outputs_valid',return_value=True), \
                 patch.object(forward,'_read_simnibs_montage',return_value=(electrodes,fids)), \
                 patch.object(forward,'_find_existing_leadfield',return_value=leadfield), \
                 patch.object(forward,'_in_leadfield_order',side_effect=lambda positions,path:positions), \
                 patch.object(forward,'_compute_leadfield',side_effect=AssertionError('FEM rerun')), \
                 patch.object(forward,'_run') as worker, \
                 patch.object(forward,'_rename_generated_outputs',return_value=expected):
                cfg=ForwardConfig()
                args=dict(head_model_dir=model,output_dir=output,output_stem='custom')
                assert forward.prepare_forward('synthetic',cfg,**args)==expected
                assert worker.call_count==0
                for shift in (0.01,0.02):
                    matrix=np.eye(4);matrix[0,3]=shift
                    transform=mne.transforms.Transform('head','mri',matrix)
                    forward.prepare_forward('synthetic',cfg,trans=transform,**args)
                    saved=mne.read_trans(output/'custom-trans.fif',verbose=False)
                    # FIF stores float32 transform values, bounding only serialization error.
                    np.testing.assert_allclose(saved['trans'],matrix,rtol=0,atol=1e-9)
                assert worker.call_count==2
    """)
