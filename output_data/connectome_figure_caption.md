# Figure caption — `connectome_figure.svg`

Hand-written companion to the hand-authored montage, kept beside it. Every
number below was read from `output_data/group_stats/*.tsv` on 2026-08-18; if the
pipeline is rerun on different data, re-check them before reusing this text.

---

**Figure 1. Functional connectomes from six deeply sampled individuals are
stable across five years, sensitive to cognitive context, and informative in
every network.** Within-network connectomes (Pearson correlation, session
level) were computed for 829 sessions across 10 CNeuroMod datasets, using the
cneuromod2026 parcellation (1134 parcels grouped into the 7 Yeo cortical
networks, cerebellum and subcortex). Sessions with at least 30 min of usable
data enter the analyses: 559 sessions from 7 datasets (`friends`,
`harrypotter`, `hcptrt`, `mario`, `movie10`, `petit-prince`, `shinobi`), all 6
subjects. Session pairs are summarised by the median Fisher-z similarity of
their connectome edges.

**(G)** Network key. Nine sagittal glass brains show the anatomical extent of
each network; their colours are used for that network throughout the figure.

**(A) Stable across five years of acquisition.** Within-subject connectome
similarity in `friends`, the most task-homogeneous dataset, as a function of
the number of seasons separating two sessions (season is the only available
time axis — sessions carry no acquisition dates). Similarity declines gently
and monotonically over a five-season lag, by 0.019 (cerebellum) to 0.043
(Limbic) — for example 0.956 to 0.935 in Vis — and every network stays far
above the between-subject floor (grey band, 0.564–0.572). Drift over years of
scanning is therefore small relative to the gap between individuals.

**(B) Captures a variety of functional brain states.** Median similarity for
the four session-pair types, per network, over all gated datasets. The ordering
within-subject/within-dataset > within-subject/between-dataset >
between-subject/within-dataset > between-subject/between-dataset holds in **9
of 9 networks** (e.g. Vis 0.95 / 0.80 / 0.69 / 0.63; Default 0.94 / 0.72 / 0.56
/ 0.45). Similarity rises with session duration, so the four bins were matched
on pair duration by construction: median pair minimum duration is 2669–2784 s
across bins, within 4%, making the contrast a task effect rather than a
duration effect.

**(C) Quality varies by network.** Within-subject similarity against median
per-network tSNR. Limbic is both the lowest-tSNR (18.6) and least similar
(0.859) network, and cerebellum and subcortex sit below the cortical networks.
*Caveat, important:* the two axes come from disjoint sets of sessions. Upstream
per-network tSNR (qa_figures `atlas_tsnr`) is exported only for `floc`,
`retinotopy` and `things` — precisely the three datasets the 30 min gate
removes — so tSNR is computed over 182 sessions of those datasets while
similarity is computed over the 559 gated sessions of the other seven. With
nine points and no shared sessions, this panel is descriptive ordering only, not
an estimate of a tSNR–similarity relationship.

**(D–F) The same contrast inside one stimulus domain.** A robustness check on
(B), not a fourth claim: "between-task" is made a far more homogeneous swap by
restricting the comparison to a single naturalistic domain — movies (friends
seasons and movie10 titles, title-level task identity; 333 sessions),
video games (`mario`, `mario3`, `mariostars`, `shinobi`; 138 sessions) and
stories (`harrypotter`, `petit-prince`; 19 sessions). Within-subject
within-task similarity still exceeds within-subject between-task similarity in
9 of 9 networks in all three domains, with a median gap of 0.022 (movies),
0.047 (video games) and 0.077 (stories). The effect is smallest for movies,
where "different task" means a different film rather than a different kind of
activity. In video games and stories the two between-subject bins are
indistinguishable in two networks each (differences ≤0.003); the stories domain
rests on 19 sessions and should be read as suggestive.

All panels: Pearson correlation, Fisher-z, gated sessions, cneuromod2026
parcellation. Axes in (A) and in (B, D–F) are truncated, with the break marked
on the frame.
