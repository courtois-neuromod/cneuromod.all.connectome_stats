# Figure caption — `connectome_figure.svg`

Hand-written companion to the hand-authored montage, kept beside it. Every
number below was read from `output_data/group_stats/*.tsv` on 2026-10-04; if the
pipeline is rerun on different data, re-check them before reusing this text.

---

**Figure 1. Functional connectomes from six deeply sampled individuals are
stable across five years, sensitive to cognitive context, and informative in
every network.** Within-network connectomes (Pearson correlation, session
level) were computed for 1128 sessions across 16 CNeuroMod datasets, using the
cneuromod2026 parcellation (1134 parcels grouped into the 7 Yeo cortical
networks, cerebellum and subcortex). Sessions with at least 30 min of usable
data enter the gated analyses: 650 sessions from 10 datasets (`friends`,
`harrypotter`, `hcptrt`, `mario`, `movie10`, `multfs`, `mutemusic`,
`narratives`, `petit-prince`, `shinobi`), all 6 subjects. Session pairs are
summarised by the median similarity of their connectome edges.

**(J)** Network key. Nine sagittal glass brains show the anatomical extent of
each network, stacked in decreasing order of stability over seasons (panel A);
their colours are used for that network throughout the figure, and panels D–I
share this order.

**(A) Stable across five years of acquisition.** Within-subject connectome
similarity in `friends`, the most task-homogeneous dataset, as a function of
the number of seasons separating two sessions (season is the only available
time axis — sessions carry no acquisition dates). Similarity declines gently
and monotonically over a five-season lag, by 0.019 (cerebellum) to 0.044
(Limbic) — for example 0.956 to 0.935 in Vis — and every network stays far
above the between-subject floor (grey), which moves only about 1%. The
design cannot separate the causes of this decline, so we report its size and
consistency only: it appears in all 6 subjects and in all 54 network x subject
cells.

**(B) The same curves, per subject.** Within-subject similarity against season
lag for each participant, averaged over networks. The six participants fall
into two non-overlapping groups at every lag (sub-03, 04, 06 above sub-01, 02,
05), a gap of about 0.015 at lag 0 against about 0.004 within each group. This
is an observation, not a group contrast: any six values split into a top and
bottom three, and with six participants it cannot be tested. No participant
trait is recorded or claimed.

**(C) Quality varies by network.** Within-subject similarity against median
per-network tSNR. Limbic is both the lowest-tSNR (17.3) and least similar
(0.857) network, and cerebellum and subcortex sit below the cortical networks.
*Caveat:* per-network tSNR (qa_figures `atlas_tsnr`) covers 11 datasets, but
not `multfs`, `petit-prince` or `shinobi`, and includes sessions the 30 min gate
removes (`floc`, `gamepad`, `langlocalizer`, `retinotopy`, `things`); tSNR is
computed over 809 sessions, similarity over the gated ones. With nine points
this panel is a descriptive ordering, not an estimate of a tSNR–similarity
relationship.

**(D) Captures a variety of functional brain states.** Median similarity for
the four session-pair types, per network, over all gated datasets. The ordering
within-subject/within-dataset > within-subject/between-dataset >
between-subject/within-dataset > between-subject/between-dataset holds in **9
of 9 networks** (e.g. Vis 0.946 / 0.773 / 0.690 / 0.615; Default 0.941 / 0.727 /
0.560 / 0.458). *Duration is not fully balanced:* similarity rises with session
duration, and median pair minimum duration is 2628 s and 2596 s for the two
within-dataset bins against 2248 s and 2268 s for the two between-dataset bins
(about 1.16x), so part of the drop for between-dataset pairs is a duration
effect. Six of the sixteen datasets (`floc`, `retinotopy`, `things`,
`gamepad`, `langlocalizer`, `triplets`) have no session above the gate and do
not contribute.

**(E–I) The same contrast inside one stimulus domain.** A robustness check on
(D), not a further claim: "between-task" is made a more homogeneous swap by
restricting the comparison to one domain — movies (friends seasons and movie10
titles, title-level task identity; 326 gated sessions), video games (`mario`,
`mario3`, `mariostars`, `shinobi`; 138), stories (`harrypotter`,
`petit-prince`; 19), taskscapes (`emotion-videos`, `triplets`, `multfs`,
`things`) and localizers (`hcptrt`, `floc`, `langlocalizer`, `retinotopy`).
Panels H and I are **ungated** (328 and 114 sessions), because the 30 min gate
leaves each a single dataset and no between-task bin; they carry the duration
confound (median pair minimum duration about 500 s for localizers' between-task
pairs against about 1800 s within-task). Within-subject within-task similarity
exceeds within-subject between-task similarity in 9 of 9 networks in every
domain, with a mean gap across networks of 0.027 (movies), 0.044 (video games),
0.079 (taskscapes), 0.101 (stories) and 0.130 (localizers), ungated. The gap
grows with how different the tasks are, but this mixes task dissimilarity with
granularity (title for movies, dataset elsewhere) and, for localizers, with
duration. The stories domain rests on 19–20 sessions and should be read as
suggestive.

All panels: Pearson correlation, gated sessions unless stated, cneuromod2026
parcellation. Axes in (A) and in (D–I) are truncated, with the break marked on
the frame.
