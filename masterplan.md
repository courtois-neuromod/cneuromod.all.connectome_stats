# CMR longitudinal fMRI validation — analysis plan

## 1. Scientific objective

The goal is to test whether functional brain organization exhibits a stable and subject-specific component across extremely heterogeneous cognitive contexts and over a longitudinal acquisition spanning approximately five years.

The dataset contains repeated fMRI acquisitions from six deeply sampled individuals. Data were collected several times per week across many distinct experiments involving very different stimuli, tasks, and cognitive constraints. The repetition time is 1.5 s. Individual runs are typically approximately 10 minutes long, and sessions generally contain several runs for a total duration of approximately 30–60 minutes.

The main hypothesis is that **conditional statistical dependencies between brain regions are substantially more stable across cognitive contexts than ordinary bivariate correlations**. Partial correlation is therefore the primary connectivity measure. Pearson correlation will be computed on exactly the same data as a comparator.

The interpretation is not that task-related activity is a contaminant superimposed on some underlying "intrinsic" process. Task and unconstrained activity are both brain activity. Rather, partial correlation conditions out activity shared across multiple regions and should therefore be less sensitive to large-scale common fluctuations induced by changing experimental constraints, physiology, noise, or other common causes.

The central result we want to establish is:

> Despite very large variation in experimental context, the conditional dependency structure of brain activity contains a stable, reproducible and strongly subject-specific component.

A secondary objective is to demonstrate that regular, Pearson's correlation show comparatively stronger task effect, while retaining a strong subject-specific component.

CNeuroMod data were acquired at 2 mm isotropic resolution with TR = 1.5 s and underwent standardized preprocessing and denoising.
The emotions-video dataset has different acquisition sequence, which will provide a particularly interesting test case for our core hypothesis regarding partial correlations.

---

## 2. Unit of analysis

### Primary unit: session

The main analysis should be performed independently for each fMRI session.

Only sessions containing at least approximately 30 minutes of usable fMRI data should enter the primary analysis.

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

## 5. connectivity measures: ordinary and partial correlation

For every session and every network, use nilearn to extract a vectorized connectome excluding diagonal. One with regular correlation, and one with partial correlation. Check in the docs, but partial correlation should really be a regularized L1 (lasso) partial correlation. We'll generate one per run, and will simply average per session in the downstream. Store all the data per dataset and per connectome measure inside an h5 file. That includes a big array where each row (or column?) is a connectome, as well as some index mechanism to retrieve subject / session / run infos. For now do not commit these h5 files in git, I want to check how big they are.

**Updated 2026-08-17: implemented as two measures, `pearson` and `partial_ledoitwolf` (Ledoit-Wolf shrinkage), computed once per session (not per run, then averaged).** An unregularized empirical-inverse variant was tried first and dropped — see section 20's amendment and CLAUDE.md, "Settled analysis decisions." This is a dataset-quality assessment, not an estimator-comparison study, so the regularized (established) estimator is primary from the start rather than something to fall back on only if the unregularized one misbehaves.


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

# ANALYSIS A — Longitudinal within-subject stability

## 9. Pairwise connectome similarity

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

Compute these for partial and Pearson correlation.

The important prediction is:

\[
SSI_{partial} > SSI_{Pearson}
\]

or, more generally, that partial correlation shows stronger subject-specific stability relative to context-induced variability.

---

# ANALYSIS B — Cross-context stability

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

If the first quantity is larger, the connectivity representation carries more information about **who the brain belongs to** than about **what experiment the person is performing**.

Repeat this comparison for Pearson and partial correlation.

The strong predicted result is that this contrast should favour subject identity more strongly for partial correlation.

---

# ANALYSIS C — Subject fingerprinting

## 12. Leave-one-session-out fingerprinting

For every held-out session:

1. Remove that session from the dataset.
2. Construct one average reference connectome for each of the six subjects from their remaining sessions.
3. Correlate the held-out connectome with each subject template.
4. Assign the identity of the template with maximum similarity.
5. Record:
   - correct/incorrect identification
   - rank of the true subject
   - similarity to true subject
   - maximum similarity to another subject
   - identification margin

Define:

\[
margin =
S_{\text{true subject}}
-
\max(S_{\text{other subjects}})
\]

Repeat for:

- partial correlation
- Pearson correlation
- each network
- full concatenated signature

Accuracy may approach ceiling because there are only six subjects, so the **identification margin and rank should be treated as important continuous outcomes**, not only accuracy.

---

## 13. Cross-task fingerprinting

This is a stronger test and should probably be one of the headline analyses.

When identifying a target session, construct each subject's template **excluding all sessions belonging to the same dataset/task as the target session**.

Therefore the classifier cannot exploit task-specific structure shared between reference and target scans.

For target session `s` from task `T`:

```text
target = subject A, task T

template A = all usable sessions from subject A excluding task T
template B = all usable sessions from subject B excluding task T
...
template F = all usable sessions from subject F excluding task T
```

Then identify the target from the six templates.

This asks directly:

> Does the subject-specific conditional-dependence structure generalize to an experimental context that was not represented in the reference data?

Compare cross-task fingerprinting for partial and Pearson correlation.

---

# ANALYSIS D — Amount of data required

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

Also compute fingerprinting accuracy/margin as a function of duration.

This directly answers:

- Is one ~10-minute run sufficient?
- Is 30 minutes sufficient?
- Does reliability continue improving substantially between 30 and 60 minutes?

This analysis is also the empirical answer to concerns about covariance estimation with approximately 150 variables.

---

# ANALYSIS E — Network-specific stability

## 15. Compare the seven networks

Run all major stability analyses separately within each functional network.

For each network compute:

- within-subject similarity
- between-subject similarity
- subject-specificity index
- cross-task fingerprinting margin
- data-length reliability curve

This may reveal that some systems contain much stronger stable individual signatures than others.

The whole-brain result should not depend entirely on one network.

---

# ANALYSIS F — Common versus individual architecture

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
- cross-task fingerprinting

using residualized connectivity.

If subject identity remains strongly detectable after removal of the shared connectivity pattern, this demonstrates that fingerprinting is driven by **stable individual deviations from the common architecture**, rather than simply by everyone sharing the same gross network organization.

Perform this for both Pearson and partial correlation.

---

# ANALYSIS G — Spatial-structure sensitivity analyses

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

Repeat the primary stability/fingerprinting analyses after removing:

- immediately adjacent parcels; and/or
- edges shorter than a selected spatial-distance threshold.

The objective is not to claim spatial dependence is artifactual. Spatial organization is part of brain organization.

The purpose is simply to demonstrate that longitudinal subject specificity is not exclusively driven by trivial local spatial coupling.

---

# ANALYSIS H — Pearson versus partial correlation

## 19. Direct comparison of the two representations

All major summary outcomes should be shown side by side:

| Outcome | Pearson | Partial correlation |
|---|---|---|
| Within-subject similarity | | |
| Different-task within-subject similarity | | |
| Between-subject similarity | | |
| Subject-specificity index | | |
| Fingerprinting accuracy | | |
| Fingerprinting margin | | |
| Cross-task fingerprinting | | |
| Minutes required for stable estimate | | |

The expected conceptual result is not necessarily that partial correlation has larger raw correlations between matrices.

The important criterion is whether it achieves a **better separation between stable individual organization and context-dependent common activity**.

A useful summary quantity is therefore:

\[
\Delta =
S_{\text{same subject,different task}}
-
S_{\text{different subject,same task}}
\]

Compare `Δ` directly between Pearson and partial correlation.

---

# ANALYSIS I — Secondary estimator robustness

## 20. Regularized partial correlation

Regularization is not part of the primary scientific hypothesis.

However, as a robustness analysis, repeat selected analyses using one or more regularized precision estimators, particularly if:

- run-level covariance matrices are poorly conditioned;
- short-duration estimates become unstable;
- some networks contain fewer usable observations than expected.

Possible alternatives:

- ridge/shrinkage covariance followed by inversion
- graphical lasso

The purpose is to establish whether the main result depends on a specific covariance estimator.

The primary session-level analysis should remain ordinary partial correlation if it behaves numerically well.

**Updated 2026-08-17: ordinary (unregularized) partial correlation did not behave numerically well and is dropped, not deferred to a robustness check.** It was tried at run-level, where `n_samples` can be smaller than `n_parcels` for the larger networks — an exactly-singular covariance, not a conditioning nuance. Ledoit-Wolf shrinkage (`partial_ledoitwolf`) is the primary measure from the start instead. This section's original framing — regularization only as a fallback robustness analysis — assumed the unregularized estimator would be well-behaved by default; that assumption didn't hold once run-level output was inspected. A further regularized estimator (e.g. graphical lasso) as a check on Ledoit-Wolf remains a valid tier-3 robustness analysis; see CLAUDE.md, "Settled analysis decisions" and "Respect the analysis hierarchy."

---

# ANALYSIS J — Quality-control dependence

## 21. Motion and usable data

For every session, relate connectome reliability to:

- mean framewise displacement
- number/proportion of censored volumes
- usable duration
- covariance condition number

Check whether low-stability sessions are systematically lower-quality acquisitions.

Repeat headline results after excluding the worst-quality sessions according to predefined QC criteria.

Do not optimize exclusion thresholds based on fingerprinting performance.

---

# ANALYSIS K — Optional longitudinal-span demonstration

## 22. Long-term generalization

The main study does not require modelling connectivity as an explicit function of elapsed time.

However, to substantiate the claim that the representation remains stable across the full multi-year acquisition, an additional analysis can use chronologically separated reference and target data.

Examples:

- construct subject templates from early acquisitions and identify later acquisitions;
- construct templates from the first half of the study and test on the second half;
- compare highly temporally separated session pairs with more closely spaced pairs.

This should remain secondary unless the exact acquisition chronology is intended to be part of the published validation dataset.

The scientific point is longitudinal persistence, not estimating a linear "effect of time."

---

# 23. Statistical inference

Because the dataset contains only six individuals but very many repeated sessions, avoid treating sessions as independent subjects.

Primary inferential quantities should therefore emphasize:

- effects replicated independently across the six participants;
- permutation/randomization tests where appropriate;
- confidence intervals obtained with participant-level resampling when possible;
- descriptive distributions of session-level effects within each subject.

For fingerprinting, evaluate the empirical null by permutation of subject labels while respecting the repeated-measures structure.

For Pearson-versus-partial comparisons, calculate the metric independently for each participant wherever possible and compare the paired six-subject values.

Avoid thousands of edge-wise hypothesis tests as the main result.

The primary claims concern **multivariate connectome stability**, not significance of individual edges.

---

# 24. Main figures envisioned

### Figure 1 — Concept and representative matrices

For one or several participants:

- Pearson connectomes from very different tasks
- partial-correlation connectomes from the same sessions

Illustrate qualitatively the greater preservation of conditional-dependence structure.

### Figure 2 — Session similarity matrices

Session × session connectivity similarity, ordered by subject and annotated by dataset/task.

Show separately:

- Pearson
- partial correlation

Stable subject-specific blocks should be visible.

### Figure 3 — Subject versus task effects

Plot distributions of:

- same subject / different task
- different subject / same task

for Pearson and partial correlation.

This is probably one of the strongest figures.

### Figure 4 — Cross-task fingerprinting

Show:

- identification accuracy
- true-subject rank
- identification margin

for Pearson versus partial correlation and possibly by network.

### Figure 5 — Data-length scaling

Reliability/fingerprinting performance versus minutes of fMRI data.

This directly establishes whether 10, 20, 30, etc. minutes are sufficient.

### Figure 6 — Network-specific results

Seven-network comparison of subject-specificity or cross-task fingerprinting.

### Supplementary figures

- covariance condition numbers
- motion dependence
- spatial-distance analyses
- exclusion of neighbouring parcels
- group-mean-residualized connectomes
- regularized precision estimators
- long-term early-versus-late analysis

---

# 25. Analysis hierarchy

The coding implementation should preserve the following hierarchy.

## Primary analyses

1. Session-level within-network partial correlation.
2. Session-level within-network Pearson correlation as comparator.
3. Within-subject versus between-subject connectome similarity.
4. Same-subject/different-task versus different-subject/same-task similarity.
5. Leave-one-session-out fingerprinting.
6. Leave-one-task/dataset-out fingerprinting.
7. Network-specific replication.

## Important secondary analysis

8. Reliability as a function of data duration/run length.

## Robustness/sensitivity analyses

9. Removal of group-average connectivity.
10. Spatial-distance dependence.
11. Exclusion of neighbouring parcels.
12. Relationship with motion/QC.
13. Regularized partial-correlation estimators.
14. Explicit long-temporal-separation analysis.

**Updated 2026-08-17: item 1 is Ledoit-Wolf-regularized partial correlation, not ordinary partial correlation** — see section 20's amendment. Item 13 in this list now refers to a *further* regularized estimator (e.g. graphical lasso) as a check on Ledoit-Wolf, not to regularization itself, which is no longer a fallback.

The coding pipeline should keep these levels distinct rather than turning every possible analysis into an equally weighted branch.

---

# 26. Core expected result

The strongest possible outcome would be:

1. Both Pearson and partial-correlation matrices contain reproducible information about individual brain organization.
2. Pearson correlation contains substantial variation associated with experimental context/common activity.
3. Partial correlation is more invariant to changing task constraints.
4. Partial-correlation connectomes identify individuals reliably even when the target session comes from an experiment absent from the reference template.
5. This subject-specific signature persists across the multi-year acquisition.
6. Approximately 30 minutes of fMRI provides a sufficiently stable estimate, with the scaling analysis establishing empirically whether useful estimates can already be obtained from individual ~10-minute runs.

The result would establish the CMR functional data as longitudinally coherent despite the deliberately heterogeneous experimental design, without requiring the existence of a privileged "resting" or "intrinsic" brain state.
