# Flex-search goal comparison on subject ernie

A worked study comparing `tit.opt.flex` optimization goals on the SimNIBS
example subject `ernie`, for two subcortical targets (thalamus, left
hippocampus):

1. **Study 1 -- goal comparison.** Six arms per target: `mean`,
   `focality_tf` at intensity weight 0 and 1, ROC `focality` with a fixed
   threshold pair, ROC `focality` with adaptive (80/20) thresholds, and
   `mean` with an optimized current ratio (`mean_ratio`).
2. **Study 2 -- mean vs. current-ratio optimization.** A slice of the
   study-1 table (`mean` vs. `mean_ratio` per target).
3. **Study 3 -- hyperparameter exploration.** One-factor-at-a-time sweep of
   the differential-evolution hyperparameters around SimNIBS's defaults,
   using `focality_tf` (w=0) on the thalamus target.

## Running it

### Notebook (recommended -- also runs the analysis and figures)

Open `flex_goals_ernie.ipynb` inside the `ti-toolbox` container / kernel.
Set the project directory before starting the kernel:

```bash
export TIT_PROJECT_DIR=/path/to/your/bids/project
```

(or edit the `PROJECT` line in the first code cell). `fetch_ernie` downloads
the example subject's finished head model into that project once. Set
`TIT_STUDY_SMOKE=1` to shrink every run to a couple of DE iterations for a
fast end-to-end smoke pass instead of the real study.

### `run_all.sh` (configs only, no analysis)

Build the JSON configs, then run them one Docker container at a time:

```bash
simnibs_python build_configs.py            # writes configs/*.json
simnibs_python build_configs.py --smoke    # writes configs_smoke/*.json (fast)

export TIT_PROJECT_DIR=/path/to/your/bids/project
./run_all.sh              # runs configs/*.json
./run_all.sh configs_smoke  # runs a different config dir
```

`run_all.sh` never runs two FEM jobs in parallel, is resumable (a config
whose `logs/timing.tsv` row already shows exit 0 is skipped), and logs each
run's stdout+stderr to `logs/<name>.log`.

## Where the results land

Inside the project's `flex-search/sub-ernie/` derivatives:

- `study_<target>_<arm>/00/` -- one finished optimizer run per study-1/2 arm
  (mesh, `flex_meta.json`, `summary.txt`, `final_sim_0/`, `final_sim_1/`).
- `hp_<factor>_<value>/00/` and `hp_default_rep<k>/00/` -- study-3 runs.
- `study1_results.csv`, `study1_figures/`, `study3_results.csv` -- written by
  the notebook's analysis cells.

`configs/` in this folder holds the real-study JSON configs (`build_configs.py`
also produces a `configs_smoke/` variant, not committed). `logs/` is
regenerated per run and is gitignored.
