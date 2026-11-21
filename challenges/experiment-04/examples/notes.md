# MoS2 thin-film route comparison — criteria dictionary

Goal: grow a 50 +/- 5 nm MoS2 film on silicon. Hard constraints: equipment limited to a tube
furnace (<=1000 C), a magnetron sputter and a CVD rig (<=1100 C); budget <=15000 CNY; time
window <=30 days; H2S needs an extra safety approval of about 5 days.

The unified comparison matrix uses the six criteria below. Direction and weight are fixed
before any value is filled, and the weights sum to 1.00.

| id | name | unit | direction | weight | why |
|---|---|---|---|---|---|
| objective_fit | Objective fit | score_1_10 | higher | 0.20 | film quality against the 50 nm target |
| total_cost | Total cost | CNY | lower | 0.20 | consumables + machine time + labour + external test + expected rework |
| total_time | Total time | day | lower | 0.15 | preparation + queue + execution + characterisation + analysis |
| feasibility | Feasibility | score_1_10 | higher | 0.20 | equipment / consumables / skill / safety approval |
| risk | Rework risk | CNY | lower | 0.15 | expected rework cost = probability x rework cost |
| evidence | Evidence strength | count | higher | 0.10 | number of independent sources behind the route |

Scoring: total_cost = consumables + machine_hours x rate + labour + external_test + rework_expected;
total_duration = preparation + queue + execution + characterisation; score = 100 x sum(weight x
normalised value) after a min-max normalisation inside the candidate set.
