---
name: bail_application
description: Bail application (regular, anticipatory, default) — grounds ordering, parity argument, S.167(2) right.
trigger_keywords: [bail, anticipatory bail, regular bail, section 437, section 438, section 439, section 167, default bail, BNSS, custody, remand, FIR, arrest, criminal]
matter_types: [bail_application, anticipatory_bail, regular_bail, default_bail]
jurisdiction: [Indian criminal courts — JMFC, Sessions Court, High Court]
---

# Bail Application Skill

## Governing Law
- Regular bail (post-arrest): CrPC S.437 (JMFC/CJM), S.439 (Sessions/HC), BNSS S.480/483
- Anticipatory bail: CrPC S.438, BNSS S.482
- Default bail (failure to file chargesheet): CrPC S.167(2), BNSS S.187(2)

## Party Labels
- Filer: **Accused** (the applicant seeking bail)
- Opposing: **State** (through Public Prosecutor)
- Never "Petitioner/Respondent" for a district bail application

## Mandatory Intake Before Drafting
- [ ] Accused's full name, age, address, occupation
- [ ] FIR number, police station, date of FIR, sections invoked
- [ ] Date of arrest and custody/remand orders (if any)
- [ ] Bail type: regular (S.437/439) or anticipatory (S.438) or default (S.167(2))
- [ ] Whether chargesheet has been filed (critical for default bail)
- [ ] Nature of offence: bailable or non-bailable; cognizable or non-cognizable
- [ ] Any prior bail applications filed and their outcome
- [ ] Co-accused's bail status (for parity argument)

## Required Sections (in this order)

```
1. court_header        → Formal court name
2. matter_particulars  → FIR No., Police Station, date, sections invoked, date of arrest
3. accused_particulars → Name, age, address, occupation, custody since, remand orders
4. brief_facts         → 3-5 paras on facts — accused's version, not prosecution's
5. grounds_for_bail    → 5-8 numbered grounds (ORDER MATTERS — see below)
6. prayer              → Release on bail with specified conditions if appropriate
7. verification        → Advocate signs (usually), not accused
```

## Grounds Ordering Rule (DESCENDING WEIGHT — always this order)

**This ordering is standard practice across Indian criminal courts. Leading with merits is a weak opener. Always lead with character, then procedure, then merits.**

```
Ground 1: First-time offender / clean antecedents / no prior criminal record
Ground 2: Full cooperation with the investigation / no flight risk
Ground 3: Deep roots in community — family, employment, property, address fixed
Ground 4: No risk of tampering with witnesses or evidence
Ground 5: Medical grounds (if applicable — always move to top if serious)
Ground 6: Employment, dependents, financial hardship
Ground 7: Parity — co-accused granted bail (cite order by name/date)
Ground 8: Merits — nature and severity of the alleged offence
```

**Why this order:** Courts look for character evidence first. A ground on "the case is weak" (merits) as the opener signals a weak application. Character grounds establish the accused as a responsible citizen first.

## Section-by-Section Drafting Instructions

### matter_particulars
> "That the applicant/accused has been arrested in connection with FIR No. [X]/[Year], registered at Police Station [Name], District [District], under Sections [X, Y, Z] of the [IPC/BNS/Special Act]. The said FIR was registered on [date] and the applicant was arrested on [date] and has been in judicial custody since [date]."

### brief_facts (3-5 paragraphs — accused's version)
> "That the applicant submits that the allegations in the FIR are false, frivolous, and motivated by [personal enmity / property dispute / business rivalry]. The applicant is innocent and has been falsely implicated."

**Important:** Never accept the prosecution's version as true in the bail application. State the accused's version clearly.

### grounds_for_bail (numbered, descending weight)
```
1. That the applicant has no prior criminal antecedents and has never been
   arrested or convicted in any criminal matter. The applicant is a
   first-time offender and the allegation is his first brush with the law.

2. That the applicant has always cooperated with the investigating agency
   and has not absconded or evaded the process of law at any stage.

3. That the applicant is a permanent resident of [address], has deep roots
   in the community, has a settled family including [spouse/children/dependents],
   and poses absolutely no risk of flight.

4. That all the witnesses in the matter are public officials / persons known
   to the police and there is no reasonable apprehension of the applicant
   tampering with any evidence or influencing any witness.

5. [Medical ground if applicable]:
   That the applicant is suffering from [condition] as evidenced by [medical
   certificate]. Continued custody poses a serious risk to the applicant's health.

6. That the applicant is the sole breadwinner of his family and his
   continued incarceration has caused extreme financial hardship to
   his dependents.

7. [Parity — if co-accused on bail]:
   That co-accused [name] has been granted bail by this Hon'ble Court /
   the Court of Sessions vide order dated [date] in [case number].
   The role attributed to the present applicant is identical or lesser
   than that of the co-accused. The applicant is entitled to parity.

8. That the alleged offence is compoundable / bailable in nature and
   the maximum sentence on conviction does not exceed [X years].
   Prima facie, the prosecution case suffers from [specific weakness].
```

### prayer
```
PRAYER

In the above facts and circumstances, it is most respectfully prayed that
this Hon'ble Court may be pleased to:

(a) Release the applicant on regular bail in connection with FIR No. [X]/[Year],
    PS [Name], under Sections [X, Y, Z] [IPC/BNS/Act], on such terms and
    conditions as this Hon'ble Court may deem fit;

(b) Pass any other order(s) as this Hon'ble Court may deem just and proper
    in the interest of justice.
```

### For default bail (S.167(2) CrPC / S.187(2) BNSS):
Add a separate opening ground:
> "That the investigation was not completed and no chargesheet has been filed within the statutory period of 60/90 days [as applicable]. The applicant is entitled to default bail as a matter of indefeasible right under Section 167(2) CrPC / Section 187(2) BNSS. Reference: *Uday Mohanlal Acharya v. State of Maharashtra* (2001) 5 SCC 453."

## Key Authorities

| Case | Citation | Proposition |
|------|----------|-------------|
| Uday Mohanlal Acharya v. State of Maharashtra | (2001) 5 SCC 453 | Default bail is an indefeasible right on failure to file chargesheet |
| Arnesh Kumar v. State of Bihar | (2014) 8 SCC 273 | Arrest must be justified; magistrate must apply mind before remand |
| Satender Kumar Antil v. CBI | (2022) 10 SCC 51 | Bail is the rule, jail the exception; must consider nature, gravity, antecedents |
| Dataram Singh v. State of UP | (2018) 3 SCC 22 | Three-pronged test: flight risk, tampering risk, repeat offence risk |
| Gudikanti Narasimhulu v. Public Prosecutor | (1978) 1 SCC 240 | Bail jurisprudence fundamentals; personal liberty is paramount |

## Conditional Sections

- **Chargesheet filed**: If chargesheet has been filed, cite compliance with S.173 CrPC and argue bail on merits
- **Default bail**: If within 60/90 days and no chargesheet, lead with S.167(2) indefeasible right ground
- **Anticipatory bail (S.438)**: Replace matter_particulars with FIR/ECIR details; add anticipatory nature statement; no custody date

## Common Errors to Avoid

1. **Leading with merits**: Never open grounds with "the case is weak" — always character first
2. **Accepting prosecution version**: Brief facts must state the accused's version, not recite FIR
3. **Wrong court**: S.437 is JMFC/CJM; S.439 is Sessions/HC; S.438 is only for anticipatory
4. **Missing parity ground**: If any co-accused is on bail, always include parity with order date/number
5. **Missing default bail ground**: If chargesheet not filed in time, S.167(2) is an absolute right — never miss it
6. **Medical grounds buried**: If medical condition exists, move it to Ground 1 or 2
