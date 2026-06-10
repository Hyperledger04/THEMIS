---
name: writ_petition
description: Writ petition under Art.226/32 — synopsis, list of dates, HC/SC mandatory sections, interim relief test.
trigger_keywords: [writ petition, article 226, article 32, high court, HC, mandamus, certiorari, prohibition, quo warranto, habeas corpus, constitutional, fundamental right, writ, PIL]
matter_types: [writ_petition, writ, public_interest_litigation, constitutional_petition]
jurisdiction: [High Courts — Art.226, Supreme Court — Art.32]
---

# Writ Petition Skill

## Governing Law
- Art. 226 — High Court jurisdiction (wider: any legal right, not just fundamental rights)
- Art. 32 — Supreme Court jurisdiction (fundamental rights only)
- High Court Rules of the relevant HC (each has its own filing rules)

## Party Labels
- Filer: **Petitioner**
- Opposing: **Respondent** (usually the State/authority)
- In public law: always "Petitioner v. State of [X] & Ors." — the State is always Respondent No. 1

## Critical Format Difference from District Court Documents

**High Court writs have sections that district court documents DO NOT:**
- **Synopsis** — 1-page narrative summary of the case and constitutional question. Read first by the bench.
- **List of Dates and Events** — chronological table, one line per event. Read before the facts.

If this is a **district court** document, omit both. If this is a **High Court or Supreme Court** writ, both are mandatory.

## Mandatory Intake Before Drafting
- [ ] Petitioner's identity and locus standi (why they can file)
- [ ] Respondent(s): State authority, statutory body, or private body with public function
- [ ] Which Article: 226 (HC) or 32 (SC)
- [ ] Which writ: mandamus / certiorari / prohibition / quo warranto / habeas corpus
- [ ] The impugned order/action/omission: exact date, authority, and what it does
- [ ] Which fundamental right / legal right has been violated
- [ ] Cause of action and its date
- [ ] Whether alternative remedies have been exhausted (if not, why writ is maintainable)
- [ ] Whether interim relief (stay) is sought

## Required Sections (strictly in this order for HC/SC)

```
1.  court_header          → Full HC/SC formal name + jurisdiction ("CRIMINAL JURISDICTION" / "CIVIL JURISDICTION")
2.  writ_petition_number  → "WRIT PETITION (CIVIL/CRIMINAL/TAX) NO. ___ OF ____"
3.  cause_title           → Petitioner(s) ... Petitioner / Respondent(s) ... Respondent
4.  synopsis              → [HC/SC ONLY] 1 page max — case narrative + constitutional question
5.  list_of_dates         → [HC/SC ONLY] Chronological table of key events
6.  questions_of_law      → Precise constitutional/legal questions for the court (2-5 questions)
7.  facts                 → Numbered body paragraphs — detailed narrative of what happened
8.  grounds               → Lettered grounds (A, B, C...) challenging the impugned order/action
9.  prayer                → Specific writs sought + interim relief if any
10. affidavit/verification → Supporting affidavit (HC requirement) or verification
```

## Section-by-Section Drafting Instructions

### synopsis (HC/SC only — 1 page max)
```
SYNOPSIS

The Petitioner, [name], [brief identity], approaches this Hon'ble Court
under Article 226 of the Constitution challenging [impugned order/action/omission]
dated [date] passed by [Respondent No. 1].

The impugned [order/action] is unconstitutional and illegal in as much as it
[summarise in 2-3 lines what is wrong with it]. The constitutional question
that arises for this Hon'ble Court's consideration is:

"[State the constitutional question in one precise sentence.]"

The Petitioner submits that the impugned [order/action] violates Article
[14/19/21/...] of the Constitution and is liable to be quashed.
```

### list_of_dates (HC/SC only)
```
LIST OF DATES AND EVENTS

Date                Event
----                -----
[DD.MM.YYYY]        [One-line description of what happened]
[DD.MM.YYYY]        [Next event]
...
[DD.MM.YYYY]        Filing of the present writ petition
```

**Rules for list of dates:**
- One line per event — no paragraphs
- Strict chronological order
- Include only legally material events (not every background fact)
- Always end with "Filing of the present writ petition"

### questions_of_law
```
QUESTIONS OF LAW

The following substantial questions of law arise for consideration:

A. Whether [the impugned order/action] violates Article [X] of the
   Constitution of India?

B. Whether [the Respondent authority] has the power to [take the impugned
   action] in the absence of [procedural safeguard / statutory authority]?

C. Whether the principles of natural justice were violated inasmuch as
   [no opportunity of hearing was given / reasons were not stated / etc.]?
```

### facts (numbered paragraphs)
Start each paragraph: "That..."
- Para 1-3: Identity of petitioner and respondent
- Para 4-8: Background facts and events in chronological order
- Para 9-12: The impugned order/action and its consequences
- Para 13+: Petitioner's attempts to seek remedy before filing writ

### grounds (lettered A, B, C...)
```
GROUNDS

A. [The impugned order] is without jurisdiction...
   because [the authority had no power under [statute] to [action]].

B. [The impugned order] is arbitrary and violates Article 14...
   because [no intelligible differentia / no rational nexus to object / etc.].

C. [The impugned order] violates the Petitioner's right under Article 21...
   because [livelihood / personal liberty / due process affected].

D. The principles of natural justice have been violated...
   because [no show-cause notice / no opportunity of hearing / no speaking order].

E. The impugned action is contrary to [specific statute/rule]...
   because [cite specific provision violated].
```

**Grounds ordering rule:** Lead with jurisdiction/vires objection first (if the authority had no power at all, that is the strongest ground). Then constitutional violations. Then procedural violations. Factual grounds last.

### prayer
```
PRAYER

In view of the above, it is respectfully prayed that this Hon'ble Court
may be pleased to:

(a) Issue a writ of [mandamus/certiorari/prohibition/habeas corpus] or any
    other appropriate writ, order, or direction quashing and setting aside
    the impugned [order/action] dated [date] passed by Respondent No. [X];

(b) [If stay sought]:
    During the pendency of the above writ petition, issue an ad interim
    stay of operation of the impugned [order/action];

(c) Award costs of the present petition to the Petitioner;

(d) Pass any other order(s) as this Hon'ble Court may deem fit and proper
    in the facts and circumstances of the case.
```

## Writs — When to Use Which

| Writ | Use when | Example |
|------|----------|---------|
| **Mandamus** | Authority refuses to perform statutory duty | "Direct the respondent to process the application" |
| **Certiorari** | Quash an order already passed | "Quash the order dated X" |
| **Prohibition** | Prevent an ongoing proceeding | "Prohibit the respondent from proceeding further" |
| **Quo Warranto** | Challenge someone's right to hold public office | "Require respondent to show by what authority" |
| **Habeas Corpus** | Illegal detention / custody | "Produce the detenu and release if detention is illegal" |

Most petitions seek mandamus + certiorari together: quash the old order AND direct a fresh compliant order.

## Conditional Sections

### Alternative remedy para (mandatory if alternative exists)
> "That the Petitioner has exhausted all alternative remedies available to him/her and has filed the present petition as no efficacious alternative remedy exists. / That the alternative remedy of [appeal/revision] is not efficacious in the present case because [the impugned order is without jurisdiction / the question raised is purely one of law / fundamental right is in issue]."

**Why mandatory:** If a statutory appeal exists, the HC will typically refuse to entertain the writ without explanation of why alternative remedy is not pursued. Failure to address this is a threshold dismissal risk.

### Interim relief (three-pronged test — required if stay is sought)
```
APPLICATION FOR AD INTERIM STAY / INTERIM RELIEF

The Petitioner humbly submits:

(i) PRIMA FACIE CASE: The Petitioner has a strong prima facie case on merits
    as the impugned order is patently without jurisdiction / violates [provision].

(ii) BALANCE OF CONVENIENCE: The balance of convenience lies in favour of the
     Petitioner as [describe harm if stay not granted]. No prejudice will be
     caused to the Respondent by grant of stay.

(iii) IRREPARABLE HARM: If stay is not granted, the Petitioner will suffer
      irreparable harm / injury which cannot be compensated in money because
      [reason — loss of employment / eviction / deprivation of fundamental right].
```

## Key Authorities

| Case | Citation | Proposition |
|------|----------|-------------|
| L. Chandra Kumar v. Union of India | (1997) 3 SCC 261 | Art. 226 HC jurisdiction is part of basic structure; cannot be ousted |
| State of UP v. Combined Chemicals | (2012) 2 SCC 303 | Mandamus lies only when statutory duty exists and authority refuses to perform |
| Whirlpool Corporation v. Registrar of Trade Marks | (1998) 8 SCC 1 | Three exceptions to alternative remedy: fundamental right, jurisdiction, natural justice |
| Maneka Gandhi v. Union of India | (1978) 1 SCC 248 | Procedure affecting Art. 21 must be fair, just, and reasonable |
| A.K. Kraipak v. Union of India | (1969) 2 SCC 262 | Foundational natural justice case — audi alteram partem + nemo judex |

## Common Errors to Avoid

1. **Missing Synopsis/List of Dates for HC**: These are mandatory for HC/SC — their absence leads to return at the registry counter
2. **Wrong writ type**: "Quash the order" requires certiorari, not mandamus; mandamus is for directing future action
3. **Alternative remedy not addressed**: If a statutory appeal exists, failure to address this is a first-listing dismissal
4. **Interim relief without three-pronged test**: A stay prayer without prima facie/balance/irreparable harm argument will be refused on the first date
5. **Grounds mixing facts and law**: Grounds should state the legal error; facts go in the facts section
6. **No locus standi**: The first paragraph must clearly establish why THIS petitioner can file (personal interest / PIL standing)
