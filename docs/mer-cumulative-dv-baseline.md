# Flight-data check of the cumulative delta-v alternative

**IAC selection decision for the current question: no-go.** Building a verified batch transport solely to demonstrate the two-sample difference from the [Basilisk replay](fprime-stateful-dv.md) would benchmark a weaker alternative for a receiver that needs only total delta-v within one accumulation epoch.

## What the nearest sources establish

- MESSENGER's Navigation to Mission Operations interface specifies three accumulated delta-v fields relative to the header's start time. The Phoenix archive describes integration inside the IMU. These are direct spacecraft precedents for carrying accumulated state instead of reconstructing it from a complete history downstream. [MESSENGER interface specification](https://pds-geosciences.wustl.edu/messenger/mess-v_h-rss-1-edr-rawdata-v1/messrs_0xxx/document/sff_sis.htm) · [Phoenix instrument archive](https://an.rsl.wustl.edu/help/Content/About%20the%20mission/PHX/Instruments/PHX%20ASE.htm).
- The ExoMars team reports that their ground preprocessing used bias correction and frame transformations, then integrated 10 Hz telemetry into 10-second inertial impulses. High-frequency detail was lost but the integrated total was preserved for their orbit determination. Their work establishes the relevance of the trade-off and does not benchmark a Linux flight-software restart. [Bellei et al., ExoMars TGO aerobraking report, pp. 5–7](https://issfd.org/ISSFD_2019/ISSFD_2019_AIAC18_Bellei-Gabriele.pdf).
- NASA PDS documents that the Spirit and Opportunity flight software accumulated rover IMU delta-v onboard and reset those registers during entry, descent and landing. The archive is a merged, irregular subset of onboard measurements. An uninterrupted accumulation reference is therefore a meaningful assumption to test. [MER IMU dataset description](https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=MER1%2FMER2-M-IMU-4-EDL-V1.0).
- For a stronger stateful receiver, Astrobee keeps IMU history and uses preintegration. Forster et al. already provide relative motion factors, covariance propagation and a posteriori bias correction. Adding an estimator alone would leave a new research claim without a differentiating contract or requirement. [NASA Astrobee IMU integration](https://nasa.github.io/astrobee/v/master/imuintegration.html) · [Forster et al., preintegration paper](https://dellaert.github.io/files/Forster16tro.pdf).

## Executed archive experiment

The script used the public Opportunity and Spirit `TRANSFORMED` tables and their PDS labels. It verified all four SHA-256 hashes, parsed declared columns and row counts, and used integer micro-metres per second for exact comparison. The two tables contained 18,226 rows. The script identified 1,691 repeated timestamps, rejected nine incomplete rows and excluded two timestamps with conflicting complete delta-v vectors. It retained one vector per remaining timestamp. A legal zero delta-v was insufficient by itself to mark a row incomplete.

The loss emulation used contiguous 0.125 s and 0.250 s runs before the first reset-like boundary in each rover. The receiver had the anchor and retained endpoint. We removed 0, 1, 3, 7 or 15 intervening published rows. The cumulative comparison subtracted the two real archive endpoints. The incremental comparison differenced consecutive published cumulative values to construct interval packets, then let the endpoint carry the last 1, 4 or 8 increments. Full incremental replay matched the reference. The increments and the reference share the archived cumulative input. This tests exactly which past intervals a representation can recover, with no independent estimate of rover navigation error. Adjacent windows overlap, and the deletion patterns are constructed.

| Rows dropped | Windows | Cumulative endpoint exact | Last 1 increment exact | Last 4 exact | Last 8 exact |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 9,537 | 9,537 | 9,537 | 9,537 | 9,537 |
| 1 | 9,337 | 9,337 | 0 | 9,337 | 9,337 |
| 3 | 9,034 | 9,034 | 0 | 9,034 | 9,034 |
| 7 | 8,626 | 8,626 | 0 | 0 | 8,626 |
| 15 | 8,458 | 8,458 | 0 | 0 | 0 |

The first received cumulative value retained the complete change in all 35,455 loss windows in the tested epochs. The fixed eight-increment packet lost information in every 15-row drop window. The test measures archived values and does not measure packet size, timing, physical restart behavior or original raw-IMU accuracy.

Across both products, the retrospective screen found four reset-like transitions. It required a prior norm of at least 10 m/s, a new norm at most 2 m/s within 500 ms, and three subsequent values remaining below the stated relative or absolute bound. The timestamps bracket signatures in the table. The PDS describes resets but the product has no independently labeled event column for assigning individual epochs. Blindly differencing adjacent vectors across the two largest transitions would yield apparent increments of 5,498.95 and 5,450.00 m/s. Those are discontinuities in the recorded counter, not physical velocity changes. Using an externally supplied epoch change, the receiver withheld the invalid difference in all 20 cross-boundary cases, including cases where the first post-boundary rows were deliberately removed. This check assumes an independently correct epoch indicator and has no mechanism for reconstructing the missing cross-epoch total.

## Consequence for the project

Preserving replica isolation might change delivery timing on a particular schedule. For the current total delta-v question, transmitting cumulative values of known provenance already removes the dependence on raw history depth within an epoch. The earlier seven-versus-five batch result is useful as a regression case for that particular raw-only pipeline. Its significance depends on a documented receiver that cannot switch to the established summary format. The epoch-boundary observation likewise needs a mission interface with a demonstrated continuity requirement, failure domain and unavailable existing solution before it could motivate a separate research project. No such interface was established here.

## Reproduce

From the repository root with Python 3.9 or later:

    python -B scripts/analyze_mer_cumulative_dv.py build/merimu_1001 results --download

The script downloads missing PDS files and checks the source content in either online or local operation. [NASA archive directory](https://pds-atmospheres.nmsu.edu/PDS/data/merimu_1001/DATA/) · [Archive cleaning counts](../results/mer-dv-archive-quality.csv) · [Loss window metrics](../results/mer-dv-loss-windows.csv) · [Reset-like boundary records](../results/mer-dv-reset-boundaries.csv)
