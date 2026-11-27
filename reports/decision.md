# Decision: where should logistics money go?

Data as of 2018-01-02: the warehouse replays the Olist history one day per real day (docs/adr/0006), so these numbers move as deliveries and reviews arrive.

Delivered orders that arrived on time or early: 39,433; late: 1,765 (4.3%).

Every day of delay costs rating until about 6 days late: from 3.87 on the promised day to 3.75 after one day and 1.87 after 6, while the 1-star share goes from 11.0% to 66.4%. After that the rating stays near 1.73. So money pays off inside the first 6 days of a delay: turning a 3-day delay into a 1-day one recovers rating; turning a 20-day delay into a 12-day one recovers almost none.

| Delivery | Orders | Reviewed | Average rating | 1-star share |
|---|---|---|---|---|
| early | 39,047 | 38,784 | 4.29 | 6.4% |
| on the promised day | 386 | 382 | 3.87 | 11.0% |
| 1 day late | 274 | 273 | 3.75 | 12.8% |
| 2 days late | 169 | 164 | 3.07 | 31.1% |
| 3 days late | 151 | 150 | 2.69 | 44.0% |
| 4 days late | 132 | 125 | 2.54 | 47.2% |
| 5 days late | 125 | 122 | 2.43 | 50.0% |
| 6 days late | 114 | 110 | 1.87 | 66.4% |
| 7 days late | 154 | 149 | 2.16 | 55.0% |
| 8 days late | 84 | 82 | 1.91 | 64.6% |
| 9 days late | 66 | 64 | 1.73 | 71.9% |
| 10 or more days late | 496 | 472 | 1.92 | 64.0% |

Late rate by purchase month peaked at 6.6% in 201704 (months 2017-01 to 2017-10, whose deliveries have had time to arrive). Correlation in observational data: late orders may differ in other ways.
