---
name: legal_contract
trigger_keywords: [contract, agreement, MOU, NDA, deed, lease, service agreement, employment agreement, vendor agreement, shareholder agreement, partnership deed, joint venture]
matter_types: [contract_review, agreement_drafting, mou, nda, deed, lease_agreement, service_agreement, employment_contract]
jurisdiction: [India - general]
---

# Legal Contract Skill

## When to Use This Skill
Use when the matter involves drafting, reviewing, or negotiating a contract, agreement, memorandum of understanding (MOU), deed, or any binding commercial arrangement. Applies to both drafting from scratch and reviewing/redlining an existing document.

## Document Types Covered
- Non-Disclosure Agreements (NDAs / Confidentiality Agreements)
- Service Agreements / Consultancy Agreements
- Employment Agreements / Offer Letters
- Vendor / Supplier Agreements
- Lease / Licence Agreements (commercial and residential)
- Memoranda of Understanding (MOUs)
- Partnership Deeds
- Shareholder Agreements
- Joint Venture Agreements
- Settlement Agreements / MoS

## Mandatory Intake Checklist
Before drafting, confirm all of the following:
- [ ] Full legal names of all parties (individual/entity, registration numbers for companies)
- [ ] Type of contract (services, goods, IP licence, employment, lease, etc.)
- [ ] Duration / term (fixed term, evergreen, project-based)
- [ ] Key commercial terms (price/fees, payment schedule, milestones)
- [ ] Jurisdiction and governing law (which state/country, which courts)
- [ ] Dispute resolution mechanism (litigation / arbitration / mediation — if arbitration: seat, rules, number of arbitrators)
- [ ] Whether stamp duty applies (state-dependent — critical for enforceability)
- [ ] IP ownership — who owns deliverables / background IP / foreground IP?
- [ ] Confidentiality obligations — mutual or one-way?
- [ ] Termination triggers — for cause, for convenience, notice period
- [ ] Liability cap and indemnity scope

## Structure Template

```
[AGREEMENT NAME]

This [AGREEMENT TYPE] ("Agreement") is entered into as of [DATE] ("Effective Date"),

BETWEEN:

[PARTY A FULL LEGAL NAME], a [company incorporated / individual] having its registered
office / residing at [ADDRESS] ("Party A" / more specific name like "Service Provider"),

AND

[PARTY B FULL LEGAL NAME], a [company incorporated / individual] having its registered
office / residing at [ADDRESS] ("Party B" / more specific name like "Client"),

(Each a "Party" and collectively the "Parties")

RECITALS

WHEREAS Party A is engaged in [brief description of business / capability];
WHEREAS Party B desires to [brief description of purpose];
NOW, THEREFORE, in consideration of the mutual covenants herein, the Parties agree:

1. DEFINITIONS
   1.1 "Confidential Information" means…
   1.2 "Deliverables" means…

2. SCOPE OF WORK / SERVICES
   2.1 [Specific obligations of each party]
   2.2 [Exclusions — what is NOT included]

3. TERM AND TERMINATION
   3.1 Effective Date and duration
   3.2 Termination for cause (with cure period)
   3.3 Termination for convenience (notice period)
   3.4 Effect of termination (survival clauses)

4. PAYMENT / CONSIDERATION
   4.1 Fees / price
   4.2 Payment schedule and due dates
   4.3 Late payment interest (typically 18% p.a. in India)
   4.4 Taxes (GST — clarify who bears TDS, GST, etc.)

5. INTELLECTUAL PROPERTY
   5.1 Background IP (pre-existing IP owned by each party)
   5.2 Foreground IP / Deliverables (who owns what is created)
   5.3 Licence grant (if ownership not transferred)

6. CONFIDENTIALITY
   6.1 Obligation
   6.2 Exclusions (public domain, prior knowledge, compelled disclosure)
   6.3 Survival period after termination

7. REPRESENTATIONS AND WARRANTIES
   7.1 Mutual representations (authority, no conflicts)
   7.2 Service Provider specific (qualified personnel, no IP infringement)

8. INDEMNIFICATION
   8.1 Each party's indemnity obligations
   8.2 Carve-outs

9. LIMITATION OF LIABILITY
   9.1 Liability cap (e.g., fees paid in last 3 months / 12 months)
   9.2 Exclusion of consequential damages
   9.3 Carve-outs from the cap (fraud, wilful misconduct, IP breach, confidentiality breach)

10. DISPUTE RESOLUTION
    10.1 Good faith negotiation / escalation (30 days)
    10.2 Arbitration clause (if chosen): seat, rules (DIAC / ICA / SIAC), arbitrators
    10.3 Governing law
    10.4 Jurisdiction (exclusive courts if litigation chosen)

11. GENERAL / BOILERPLATE
    11.1 Entire Agreement / Integration clause
    11.2 Amendment (must be in writing, signed)
    11.3 Waiver
    11.4 Severability
    11.5 Notices
    11.6 Force Majeure
    11.7 Assignment (typically restricted without consent)
    11.8 Counterparts / Electronic signatures

SCHEDULE A — [Scope of Work / Statement of Work]
SCHEDULE B — [Fees and Payment Schedule]
SCHEDULE C — [Key Personnel / Contacts]

IN WITNESS WHEREOF, the Parties have executed this Agreement as of the date first written above.

[PARTY A]                               [PARTY B]
By: ___________________________         By: ___________________________
Name:                                   Name:
Title:                                  Title:
Date:                                   Date:
```

## Risk Flags
- **HIGH:** Stamp duty — contracts not stamped per the applicable State Stamp Act are inadmissible as evidence. Identify the applicable state, compute duty, and advise on stamping before execution.
- **HIGH:** Arbitration clause defects — an ambiguous arbitration clause (e.g., "disputes may be referred to arbitration") is non-binding. Use mandatory language: "shall be referred to arbitration."
- **HIGH:** IP assignment vs. licence — if the client wants ownership of deliverables, the clause must say "assigns" not "licences." Both parties must sign an assignment deed (S.19 Copyright Act requires written assignment).
- **HIGH:** GST / TDS — contracts must address who bears GST and TDS. An omission leads to disputes on net pay.
- **MEDIUM:** Liability cap — "fees paid in the last 3 months" is often too low for long-term contracts. Negotiate to 12 months or total contract value.
- **MEDIUM:** Non-compete / non-solicitation — enforceable only for the duration of the contract in India (post-termination restraints on trade are void under S.27 Indian Contract Act 1872, except for sale of business goodwill).
- **MEDIUM:** Force Majeure — post-COVID, include pandemics, government actions, and cyberattacks explicitly.
- **LOW:** Counterparts clause — without it, both parties must sign the same physical copy. With it, separate signed PDFs are valid.

## Key Statutes
- Indian Contract Act, 1872 (formation, validity, breach, remedies)
- Specific Relief Act, 1963 (S.10 — specific performance; S.14 — contracts not specifically enforceable)
- Arbitration and Conciliation Act, 1996 (arbitration clauses, enforcement)
- Information Technology Act, 2000 (electronic signatures — S.5; electronic contracts — S.10A)
- Copyright Act, 1957 (S.19 — assignment of copyright must be in writing)
- Indian Stamp Act, 1899 + applicable State Stamp Act (stamp duty)
- Goods and Services Tax Act, 2017 (GST on services)

## Output Rules
- Always define every capitalised term the first time it is used
- Use numbered clauses (1., 1.1, 1.1.1) — never use bullet points in the operative clauses
- Include a definitions section at the top
- Schedules for commercial terms (scope, fees, SLAs) — keep them separate from the body so they can be updated without re-executing the full agreement
- State governing law and seat of arbitration in the same clause
- Bold the clause headings for readability
- Flag any high-risk items for the lawyer's attention with [FLAG: ...] inline
