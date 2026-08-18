# CMR longitudinal fMRI validation — analysis plan

## 1. Scientific objective

**Updated 2026-08-18: the goal is now three claims about CNeuroMod as a functional-connectome resource, established with Pearson correlation only.** The original hypothesis below (partial correlation as the primary measure, subject fingerprinting as a headline outcome) was tested against the first real run (11 datasets, 829 sessions, `cneuromod2026`, both measures computed) and rejected as a headline result — see section 5's amendment for the numbers. This section keeps the original framing for the record, followed by what actually replaced it.

The dataset contains repeated fMRI acquisitions from six deeply sampled individuals. Data were collected several times per week across many distinct experiments involving very different stimuli, tasks, and cognitive constraints. The repetition time is 1.5 s. Individual runs are typically approximately 10 minutes long, and sessions generally contain several runs for a total duration of approximately 30–60 minutes.

The interpretation is not that task-related activity is a contaminant superimposed on some underlying "intrinsic" process. Task and unconstrained activity are both brain activity. **This part of the original interpretation still holds** and must not be undone by the claims below: they are about data-quality and stability, not about isolating an "intrinsic" state.

### What is actually established now

Three claims, all Pearson-only, all computed by `analysis/group_stats.py` (`invoke run-group-stats`):

1. **Stable across five years of acquisition** — the friends longitudinal analysis (formerly ANALYSIS A): within-subject similarity across `friends` seasons decays gently with acquisition lag against a clear between-subject floor.
2. **Captures a variety of functional brain states** — the cross-context analysis (formerly ANALYSIS B): across all datasets, within-subject/within-task similarity exceeds within-subject/between-task, which exceeds between-subject/within-task, which exceeds between-subject/between-task, in every network.
3. **Applies to all networks, with varying quality** — both analyses above, replicated per network (formerly ANALYSIS E, now folded into the headline rather than a separate analysis) and related to per-network tSNR.

No fingerprinting (formerly ANALYSIS C — never implemented, and dropped along with partial correlation as a headline measure) and no partial-correlation headline comparison (formerly ANALYSIS H — see section 5).

### Original hypothesis (superseded, kept for the record)

The main hypothesis was that **conditional statistical dependencies between brain regions are substantially more stable across cognitive contexts than ordinary bivariate correlations**, with partial correlation as the primary connectivity measure and Pearson as the comparator:

> Despite very large variation in experimental context, the conditional dependency structure of brain activity contains a stable, reproducible and strongly subject-specific component.

A secondary objective was to demonstrate that Pearson correlation shows a comparatively stronger task effect while retaining a subject-specific component — this part is **weakly, directionally supported** by the same run that rejected partial correlation as a headline measure (section 5), but the reliability cost was judged not worth carrying.

CNeuroMod data were acquired at 2 mm isotropic resolution with TR = 1.5 s and underwent standardized preprocessing and denoising.

---

## 2. Unit of analysis

### Primary unit: session

The main analysis should be performed independently for each fMRI session.

**Updated 2026-08-18: the usable-data gate is `usable_duration_sec >= 600` (10 minutes), not 30.** A 30-minute bar was tested against the real per-session QC and rejected: it deletes `floc` (0/18 sessions), `retinotopy` (0/23) and `things` (0/141) entirely — three of the ten task contexts, and the three least like the naturalistic datasets. At 600 s, 803 of 829 sessions survive and only `floc` drops out on duration alone. `run-group-stats` reports every headline table both gated and ungated. See CLAUDE.md, "Settled analysis decisions".

**Updated 2026-08-18 (supersedes the amendment above): the gate is `usable_duration_sec >= 1800` (30 minutes) after all — reversed for a reason unrelated to sample size.** Measured from the connectome h5 indexes, the 600 s gate leaves the cross-context contrast (claim 2) duration-confounded: median pair min-duration was ~2661–2692 s for the two within-task bins versus ~1701–1706 s for the two between-task bins, a ~1.6x imbalance, and similarity rises with duration independent of any task effect. At 1800 s the four bins come within ~4% of each other (~2668–2784 s), so the contrast is interpretable as a task effect. This was chosen from pair-duration composition, an acquisition/design property computed with no reference to similarity values — not a threshold tuned against similarity contrasts, which remains forbidden. `floc`, `retinotopy` and `things` now leave claim 2 entirely (as they did at the rejected 30-minute bar above, for the same reason); 559 of 829 sessions survive, all 6 subjects retained, across `friends, harrypotter, hcptrt, mario, movie10, petit-prince, shinobi`. `run-group-stats` writes the pair-duration comparison to `duration_balance.tsv` and still reports every headline table gated and ungated. See CLAUDE.md, "Settled analysis decisions".

Approximate sample counts are:

- 10 minutes: ~400 volumes
- 30 minutes: ~1,200 volumes
- 45 minutes: ~1,800 volumes
- 60 minutes: ~2,400 volumes

The primary analysis should therefore have substantially more temporal observations than parcels within each network.

### Secondary unit: run

Individual ~10-minute runs should also be analysed separately, but primarily to determine how much data are required before the connectivity estimates become stable.

Run-level results should not replace the session-level analysis.

**Updated 2026-08-17: `run-connectomes` computes session-level connectomes only.** A first implementation also computed a standalone connectome per run, but for the larger networks (Default: 209 parcels, SomMot: 194) run-level `n_samples` can be smaller than `n_parcels`, which is exactly the pathological case for an unregularized estimator (see section 20's amendment) and was producing a large share of pipeline runtime for output this data-quality assessment does not need. If the duration-scaling question in Analysis D is pursued, it should truncate session-concatenated time series to a coarse grid of durations rather than rely on a stored per-run connectome — see CLAUDE.md, "Settled analysis decisions".

---

## 3. Parcellation

**Updated 2026-08-17: primary parcellation is `cneuromod2026` (1134 parcels: cortex + subcortex + cerebellum), not the ~1,000-region cortical-only parcellation this section originally described.** See CLAUDE.md, "Settled analysis decisions", for the full rationale — it lines up with what the qa_figures QC tables cover. The code stays parcellation-agnostic, so the original ~1,000-region cortical parcellation (`schaefer1000`) still works and is what the smoke test uses.

Each parcel belongs to one of **nine** large-scale groups: the seven Yeo cortical networks (~150 parcels each), `cerebellum` (88 parcels), and `subcortex` (50 parcels, all pooled as one network).

The **primary partial-correlation analysis should be performed independently within each network**.

For a network containing `p` parcels, estimate a `p × p` covariance matrix from the parcel time series and obtain the corresponding precision matrix.

This is important computationally and statistically: the primary analysis should **not silently attempt to invert a covariance matrix over the whole parcellation**.

The result for each session (and, secondarily, each run) is therefore nine within-network partial-correlation matrices (seven for schaefer1000).

Cross-network edges are not part of the primary analysis.

A full whole-brain regularized precision matrix can be explored later as a secondary analysis.

---

## 4. Input time series and preprocessing

Use the existing standardized CMR/CNeuroMod denoised time series.
Those come fully preprocessed.

For each run:

1. Load parcel-average BOLD time series.
2. Standardize each parcel time series within the run (zscore in nilearn)
3. Retain the number of volumes.
4. Find the corresponding QC stats for the run.

Runs belonging to the same session can then be concatenated after run-wise preprocessing/standardization.

Do not concatenate raw, non-standardized runs because run-specific means or scaling differences could themselves induce correlations.

Record for every session:

- subject
- dataset/task
- run IDs
- number of runs
- duration
- usable duration
- number of retained volumes
- mean/median framewise displacement or equivalent motion summary
- the tsnr per network.

---

## 5. connectivity measures: Pearson and partial correlation

For every session and every network, use nilearn to extract a vectorized connectome excluding diagonal. One with regular correlation, and one with partial correlation. Check in the docs, but partial correlation should really be a regularized L1 (lasso) partial correlation. We'll generate one per run, and will simply average per session in the downstream. Store all the data per dataset and per connectome measure inside an h5 file. That includes a big array where each row (or column?) is a connectome, as well as some index mechanism to retrieve subject / session / run infos. For now do not commit these h5 files in git, I want to check how big they are.

**Updated 2026-08-17: implemented as two measures, `pearson` and `partial_ledoitwolf` (Ledoit-Wolf shrinkage), computed once per session (not per run, then averaged).** An unregularized empirical-inverse variant (`partial_empirical`) was tried first and dropped: at run level, `n_samples` can be smaller than `n_parcels` for the larger networks (Default has 209 parcels, SomMot 194), making the sample covariance exactly singular — a routine failure, not a conditioning nuance. Ledoit-Wolf shrinkage (`partial_ledoitwolf`) became the primary partial-correlation estimator from the start instead of something to fall back on only if the unregularized one misbehaved. A further regularized estimator (e.g. graphical lasso) as a check on Ledoit-Wolf remains a valid robustness analysis (see section 25).

**Updated 2026-08-18: partial correlation is no longer a headline measure at all — only `pearson` is read by `run-group-stats` (`analysis_measure` in `invoke.yaml`).** The first real run (11 datasets, 829 sessions, `cneuromod2026`, both measures) settled the original hypothesis (section 1). Median session-pair similarity, all datasets:

| measure | within-subj/within-task | within-subj/between-task | between-subj/within-task | between-subj/between-task |
|---|---|---|---|---|
| pearson (Vis) | 0.943 | 0.782 | 0.685 | 0.619 |
| pearson (Default) | 0.931 | 0.725 | 0.551 | 0.452 |
| partial (Vis) | 0.724 | 0.627 | 0.504 | 0.476 |
| partial (Default) | 0.638 | 0.541 | 0.425 | 0.392 |

Partial correlation's between-subject floor is barely below Pearson's, while its within-subject ceiling collapses from ~0.93 to ~0.65–0.75 — the dynamic range is roughly halved. It is modestly less task-sensitive in relative terms (task costs ~30% of its subject span vs. ~42% for Pearson — weak, directional support for the original hypothesis), but that buys little against a large cost in reliability, and none of the three claims in section 1 need it. `partial_ledoitwolf` is still computed and stored by `run-connectomes` (`connectome_measures` in `invoke.yaml`) so the comparison stays reproducible, and the 543 MB of existing connectome files were left untouched — only the *analysis* became Pearson-only.


## 8. Basic visualization

For each subject, select representative sessions drawn from very different experiments.

Plot:

- partial-correlation matrices
- Pearson-correlation matrices

Sort parcels consistently by network and anatomical/parcellation ordering.

Also compute and display:

- group-average partial-correlation matrix
- each subject's average partial-correlation matrix
- group-average Pearson matrix
- each subject's average Pearson matrix

The expected qualitative pattern is:

1. a strong shared architecture across all subjects;
2. reproducible deviations specific to each individual;
3. greater session/task variation for Pearson than for partial correlation.

---

# Friends longitudinal analysis (claim 1; formerly ANALYSIS A)

## 9. Pairwise connectome similarity

**Updated 2026-08-18: implemented restricted to `friends` only, split by season lag rather than generic "acquisition period."** `friends` is the most task-homogeneous dataset available (every run is a Friends episode) and its six locally available seasons were acquired in order across most of the project, so the season split isolates drift (scanner, subject state, elapsed time — session ordinal is the only available time axis, there are no acquisition dates) from cognitive context, which the cross-context analysis (below) cannot. See `analysis/friends_seasons.py` and `analysis/group_stats.py`'s `longitudinal_summary`.

For every pair of sessions, compute similarity between their connectivity signatures.

Primary matrix-similarity metric:

\[
S(a,b)=corr(z_a,z_b)
\]

where `z_a` and `z_b` are vectorized Fisher-transformed edges.

Compute this separately for:

- partial correlation
- Pearson correlation
- each of seven networks
- concatenated whole-session signature

This produces a session × session similarity matrix.

Annotate each session with:

- subject
- dataset/task
- acquisition period if available internally

---

## 10. Within-subject versus between-subject similarity

Split all session pairs into:

### Within-subject pairs

Two sessions from the same participant.

### Between-subject pairs

Sessions from different participants.

Compare the distributions.

Primary quantities:

- mean within-subject similarity
- mean between-subject similarity
- difference between them
- effect size
- subject-specificity index:

\[
SSI =
S_{\text{within subject}}
-
S_{\text{between subject}}
\]

**Updated 2026-08-18: computed for Pearson only** — see section 5's amendment for why partial correlation was dropped as a headline measure. The SSI-comparison prediction below (`SSI_partial > SSI_Pearson`) is superseded by that amendment's numbers, kept here for the historical record:

Compute these for partial and Pearson correlation.

The important prediction was:

\[
SSI_{partial} > SSI_{Pearson}
\]

or, more generally, that partial correlation shows stronger subject-specific stability relative to context-induced variability.

---

# Cross-context analysis (claim 2; formerly ANALYSIS B)

## 11. Same-task and different-task comparisons

Further divide session pairs according to experimental context:

1. same subject / same task or dataset
2. same subject / different task or dataset
3. different subject / same task or dataset
4. different subject / different task or dataset

This is crucial because subject identity and experimental context are competing sources of similarity.

A particularly informative comparison is:

\[
S(\text{same subject, different task})
\]

versus

\[
S(\text{different subject, same task})
\]

If the first quantity is larger, the connectivity representation carries more information about **who the brain belongs to** than about **what experiment the person is performing**. This is claim 2 (section 1) — verified in every one of the nine networks with Pearson correlation.

**Updated 2026-08-18: computed for Pearson only**; the predicted Pearson-vs-partial contrast below is superseded by section 5's amendment, kept for the historical record:

Repeat this comparison for Pearson and partial correlation.

The strong predicted result was that this contrast should favour subject identity more strongly for partial correlation.

---

**Updated 2026-08-18: subject fingerprinting (formerly ANALYSIS C — leave-one-session-out and cross-task/leave-one-task-out identification) was never implemented and is dropped, not deferred.** It was part of the original hypothesis's headline outcomes (section 1), but none of the three claims that replaced it need an identification/classification framing — they are stated directly as similarity contrasts. If a future need for fingerprinting-style validation arises, revisit deliberately rather than reviving this section unchanged.

---

# ANALYSIS D — Amount of data required (robustness)

**Updated 2026-08-18: kept as a robustness analysis, not a headline claim.** There is also a concrete duration confound in claim 2 (the cross-context analysis) worth flagging here: similarity rises with session duration, and median usable duration varies ~7x across datasets (floc 434 s, retinotopy 694 s, things 1246 s, … harrypotter 5044 s), so part of the between-task drop in claim 2 is a duration effect, not a pure task effect. Handle it by **reporting** median usable duration alongside every per-dataset number (`session_gate.tsv`) and adding a duration-matched sensitivity row, not by introducing a duration-correction model — see CLAUDE.md, "Respect the analysis hierarchy."

**Updated 2026-08-18 (partial discharge): the usable-data gate rose to 1800 s (section 2's amendment) specifically to equalise pair duration across the four cross-context bins, which discharges the coarse version of this confound directly** — at 600 s the within-task/between-task pair-duration ratio was ~1.6x; at 1800 s it is ~1.04x (`duration_balance.tsv`). What remains as a genuine robustness item is the finer-grained version: truncation-based exact duration matching (subsample every session's timeseries down to a common duration before estimating its connectome), which needs recomputed connectomes and is not implemented by the gate change alone. `session_gate.tsv` still reports median usable duration per dataset for both gates as the standing sensitivity comparison.

## 14. Stability as a function of acquisition duration

Estimate how connectivity reliability changes with the amount of data.

Target durations could include approximately:

- 5 min
- 10 min
- 20 min
- 30 min
- 45 min
- 60 min

Only include durations supported by the available session.

For each target duration:

1. repeatedly subsample the appropriate amount of data from longer sessions;
2. estimate partial and Pearson connectivity;
3. compare the estimate against a high-data reference connectome for that subject;
4. repeat across sessions and subjects.

Where possible, draw samples from complete/contiguous run segments rather than arbitrary disconnected volumes.

Primary output:

\[
\text{connectome similarity to reference}
\quad\text{vs}\quad
\text{minutes of data}
\]

This directly answers:

- Is one ~10-minute run sufficient?
- Is 30 minutes sufficient?
- Does reliability continue improving substantially between 30 and 60 minutes?

This analysis is also the empirical answer to concerns about covariance estimation with approximately 150 variables.

---

**Updated 2026-08-18: network-specific stability (formerly ANALYSIS E) is folded into the headline as claim 3, not a separate analysis** — both `cross_context.tsv` and `longitudinal_bins.tsv` are already `network × bin × gate` tables, replicated across all nine networks (`network_quality.tsv` adds the tSNR relationship). See section 1, claim 3.

---

# ANALYSIS F — Common versus individual architecture (robustness)

## 16. Remove the shared group connectome

A possible concern is that session similarity is dominated by a large spatial/network architecture common to everyone.

Calculate the average connectome across subjects/sessions:

\[
C_{group}
\]

For every session:

\[
C_{residual}=C_{session}-C_{group}
\]

Preferably construct the group mean in a leave-one-subject-out fashion when evaluating a participant.

Repeat:

- within/between-subject similarity
- the cross-context similarity contrast (claim 2)

using residualized connectivity.

If subject identity remains strongly detectable after removal of the shared connectivity pattern, this demonstrates that the effect is driven by **stable individual deviations from the common architecture**, rather than simply by everyone sharing the same gross network organization.

**Updated 2026-08-18: Pearson only** — see section 5's amendment.

---

# ANALYSIS G — Spatial-structure sensitivity analyses (robustness)

## 17. Anatomical distance

Partial correlations may still be influenced by spatial proximity, shared vasculature, smoothing, partial-volume effects or signal leakage.

For every parcel pair, calculate physical distance between parcel centroids where meaningful.

Characterize:

\[
|\rho_{partial}| \quad \text{vs distance}
\]

and connectivity stability versus distance.

Bin edges into distance ranges and calculate subject-specificity separately in each bin.

Possible bins can be selected based on the empirical distance distribution rather than imposed arbitrarily.

---

## 18. Exclusion of neighbouring parcels

Repeat the primary stability analyses after removing:

- immediately adjacent parcels; and/or
- edges shorter than a selected spatial-distance threshold.

The objective is not to claim spatial dependence is artifactual. Spatial organization is part of brain organization.

The purpose is simply to demonstrate that the stability effect is not exclusively driven by trivial local spatial coupling.

**Updated 2026-08-18: Pearson only** — see section 5's amendment. A further regularized partial-correlation estimator (e.g. graphical lasso) as a check on `partial_ledoitwolf` remains a valid robustness analysis in its own right (formerly ANALYSIS I, folded into section 5's amendment and the hierarchy in section 25) — but it checks the *stored, reproducible* comparator, not a headline result.

---

# ANALYSIS J — Quality-control dependence (robustness)

## 21. Motion and usable data

For every session, relate connectome reliability to:

- mean framewise displacement
- number/proportion of censored volumes
- usable duration
- covariance condition number

Check whether low-stability sessions are systematically lower-quality acquisitions.

Repeat headline results after excluding the worst-quality sessions according to predefined QC criteria.

**Updated 2026-08-18: implemented as the `usable_duration_sec >= 600` gate in `run-group-stats`** (section 2's amendment); every headline table is reported gated and ungated. **Do not optimize exclusion thresholds based on similarity contrasts** (rephrased from the original "fingerprinting performance" now that fingerprinting is dropped — the principle is unchanged: pick thresholds a priori from QC, not from how good the headline result looks).

---

# ANALYSIS K — Optional longitudinal-span demonstration (robustness)

## 22. Long-term generalization

The main study does not require modelling connectivity as an explicit function of elapsed time.

However, to substantiate the claim that the representation remains stable across the full multi-year acquisition, an additional analysis can use chronologically separated reference and target data.

Examples:

- construct subject templates from early acquisitions and identify later acquisitions;
- construct templates from the first half of the study and test on the second half;
- compare highly temporally separated session pairs with more closely spaced pairs.

This should remain secondary unless the exact acquisition chronology is intended to be part of the published validation dataset.

The scientific point is longitudinal persistence, not estimating a linear "effect of time."

**Updated 2026-08-18: the core mechanism is now claim 1 itself** (the friends longitudinal analysis, section "Friends longitudinal analysis" above) — season lag against the between-subject floor already is the season-ordinal version of "chronologically separated reference and target." What remains here as a genuinely separate robustness check is the early-versus-late split across *all* datasets, not just `friends`.

---

# 23. Statistical inference

Because the dataset contains only six individuals but very many repeated sessions, avoid treating sessions as independent subjects.

Primary inferential quantities should therefore emphasize:

- effects replicated independently across the six participants;
- permutation/randomization tests where appropriate;
- confidence intervals obtained with participant-level resampling when possible;
- descriptive distributions of session-level effects within each subject.

**Updated 2026-08-18: no fingerprinting and no Pearson-versus-partial comparison remain as headline results** (sections 1 and 5's amendments), so the two paragraphs that referenced them are removed. The inference rules above are unchanged and still apply to all three claims: permutation tests, participant-level resampling, and replication across the six individuals — not thousands of edge-wise tests.

Avoid thousands of edge-wise hypothesis tests as the main result.

The primary claims concern **multivariate connectome stability**, not significance of individual edges.

---

# 24. Main figures envisioned

**Updated 2026-08-18: superseded by the three real montage panels `notebooks/figure_connectomes.ipynb` renders from `output_data/group_stats/*.tsv`** (`connectome_figure.svg` is the layout source of truth). Figure 4 (cross-task fingerprinting) is deleted along with fingerprinting itself (section 1's amendment); the rest are retitled to match the three claims rather than the Pearson-vs-partial framing:

### Panel 1 — Friends longitudinal (claim 1)

Within-subject Pearson similarity vs. friends season lag, one line per network, against the between-subject band. Implemented as `figures/figure_connectomes/longitudinal.png`.

### Panel 2 — Cross-context (claim 2)

The four same-/different-subject x same-/different-dataset bins, all datasets, all nine networks. Implemented as `figures/figure_connectomes/cross_context.png`.

### Panel 3 — Network quality (claim 3)

Per-network within-subject stability against median tSNR, falling back to a labelled ordering plot with a coverage note when tSNR coverage is too thin. Implemented as `figures/figure_connectomes/network_quality.png`.

### Diagnostic outputs (not montage panels)

3x3 per-network density grids for both analyses (`{analysis}_{measure}_histograms.png`), from `pair_histograms.tsv` — the equivalent of the original Figure 1/2 concept, kept as a diagnostic rather than a headline panel.

### Supplementary figures (robustness tier, sections D/F/G/J/K)

- covariance condition numbers
- motion dependence
- spatial-distance analyses
- exclusion of neighbouring parcels
- group-mean-residualized connectomes
- regularized precision estimators
- long-term early-versus-late analysis
- duration-matched sensitivity check on the cross-context/duration confound

---

# 25. Analysis hierarchy

**Updated 2026-08-18: collapsed to two tiers, matching `analysis/group_stats.py` and CLAUDE.md, "Respect the analysis hierarchy."** The original three-tier list (primary partial-vs-Pearson fingerprinting hierarchy, a duration secondary tier, and a robustness tier) is superseded — fingerprinting and the partial-correlation comparison are dropped (sections 1, 5), and network-specific replication is folded into the primary tier rather than listed separately.

## Primary analyses

1. Cross-context similarity (claim 2): session-level, within-network, Pearson only — within- versus between-subject connectome similarity, and same-subject/different-task versus different-subject/same-task similarity, gated and ungated.
2. Friends longitudinal stability (claim 1): the same similarity machinery restricted to `friends`, split by season lag instead of dataset.
3. Per-network replication of both (claim 3): both analyses above are already `network × bin × gate` tables across all nine networks, related to per-network tSNR.

## Robustness/sensitivity analyses

4. Reliability as a function of data duration/run length, and the duration-matched sensitivity check on the cross-context/duration confound (ANALYSIS D).
5. Removal of group-average connectivity (ANALYSIS F).
6. Spatial-distance dependence and exclusion of neighbouring parcels (ANALYSIS G).
7. Relationship with motion/QC beyond the `usable_duration_sec` gate (ANALYSIS J).
8. A further regularized partial-correlation estimator (e.g. graphical lasso) as a check on `partial_ledoitwolf` (formerly ANALYSIS I).
9. Explicit early-versus-late temporal separation across all datasets, not just `friends` (ANALYSIS K).

The coding pipeline should keep these levels distinct rather than turning every possible analysis into an equally weighted branch — a robustness analysis does not get promoted into the pipeline's main path because it was interesting to implement.

---

# 26. Core expected result

**Updated 2026-08-18: this is what the first real run actually established (section 5's amendment), not the original aspirational outcome kept below for the record.**

1. Pearson-correlation connectomes contain reproducible, subject-specific information: within-subject similarity clearly exceeds between-subject similarity, in every network (claim 2).
2. That similarity survives large context changes — same-subject/different-task pairs exceed different-subject/same-task pairs, in every network (claim 2).
3. The subject-specific signature persists across the multi-year acquisition, decaying only gently with season lag against a stable between-subject floor (claim 1).
4. Quality varies systematically by network and relates to tSNR where qa_figures covers it, but the effect above holds broadly across networks (claim 3).
5. Partial correlation does **not** improve on this — its between-subject floor is barely below Pearson's while its within-subject ceiling collapses, roughly halving the dynamic range (section 5). It is retained only as a stored, reproducible comparator, not a result.

### Original aspirational outcome (superseded, kept for the record)

1. Both Pearson and partial-correlation matrices contain reproducible information about individual brain organization.
2. Pearson correlation contains substantial variation associated with experimental context/common activity.
3. Partial correlation is more invariant to changing task constraints.
4. Partial-correlation connectomes identify individuals reliably even when the target session comes from an experiment absent from the reference template.
5. This subject-specific signature persists across the multi-year acquisition.
6. Approximately 30 minutes of fMRI provides a sufficiently stable estimate, with the scaling analysis establishing empirically whether useful estimates can already be obtained from individual ~10-minute runs.

The result establishes the CMR functional data as longitudinally coherent despite the deliberately heterogeneous experimental design, without requiring the existence of a privileged "resting" or "intrinsic" brain state.
