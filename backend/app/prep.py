"""Cleaning rules applied to a client's raw files before they are loaded into the query database.

Each rule reflects a decision made about the data export. All steps tolerate missing files, so partial
uploads still load. Rules are global for now; make them per-client when a second client needs different ones.
"""
import html
import re

import pandas as pd

# Only these activity types are analysed; everything else (Announcement, ProfilePopulation, Project, Impact) is dropped.
ACTIVITY_TYPES = {
    "SurveyActivity": "Survey",
    "DiscussionActivity": "Discussion",
    "ConversationActivity": "Conversation",
    "SimpleSurveyActivity": "Simple Survey",
    "QuickPollActivity": "Quick Poll",
}
EXCLUDED_MEMBERSHIP_STATUS = {"Removed - LowQuality"}
# Profile fields to leave out: PII, plus internal/operational fields that aren't demographics.
EXCLUDED_PROFILE_FIELDS = {"firstname", "lastname", "vtx-articulationcheck", "vtx-holdflags", "vtx-incentiveeligibility"}

_TAG = re.compile(r"<[^>]+>")


def _strip_html(s):
    if not isinstance(s, str):
        return s
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", s))).strip()


def _dates(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        if c.lower().endswith("date"):
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def _clean_field(name: str) -> str:
    n = re.sub(r"^vtx-", "", str(name).strip(), flags=re.I)
    return re.sub(r"[^0-9a-z]+", "_", n.lower()).strip("_")


def clean(f: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    f = {k: v.copy() for k, v in f.items()}

    # activities: keep the 5 analysed types, de-duplicate, plain-text descriptions, friendly type names
    if "activities" in f:
        a = f["activities"]
        a = a[a["ActivityType"].isin(ACTIVITY_TYPES)].drop_duplicates("ActivityId")
        a["ActivityType"] = a["ActivityType"].map(ACTIVITY_TYPES)
        for c in ("ActivityName", "ActivityDescription"):
            if c in a:
                a[c] = a[c].map(_strip_html)
        f["activities"] = _dates(a)
    valid_activities = set(f["activities"]["ActivityId"]) if "activities" in f else None

    # members: drop low-quality removals and the affiliated column
    if "members" in f:
        m = f["members"]
        m = m[~m["MembershipStatus"].isin(EXCLUDED_MEMBERSHIP_STATUS)].drop(columns=["AffiliatedStatus"], errors="ignore")
        f["members"] = _dates(m)
    valid_members = set(f["members"]["MemberId"]) if "members" in f else None

    def restrict(df: pd.DataFrame) -> pd.DataFrame:
        if valid_members is not None:
            df = df[df["MemberId"].isin(valid_members)]
        if valid_activities is not None and "ActivityId" in df:
            df = df[df["ActivityId"].isin(valid_activities)]
        return df

    # member profile: long -> wide (one row per member), demographics only, no names
    if "member_profile" in f:
        p = f["member_profile"]
        p = p[~p["ProfileFieldName"].str.strip().str.lower().isin(EXCLUDED_PROFILE_FIELDS)]
        p = p[p["MemberId"].isin(valid_members)] if valid_members is not None else p
        p = p.assign(ProfileFieldName=p["ProfileFieldName"].map(_clean_field))
        wide = p.pivot_table(index="MemberId", columns="ProfileFieldName", values="ProfileFieldValue",
                             aggfunc="first").reset_index()
        wide.columns.name = None
        f["member_profile"] = wide

    # closed ends: only members/activities in scope; use the answer text; drop the internal response-code id
    if "closed_ends" in f:
        c = restrict(f["closed_ends"]).drop(columns=["ResponseCode"], errors="ignore")
        c = c[c["AnswerLabel"].notna()]
        c["QuestionText"] = c["QuestionText"].map(_strip_html)
        f["closed_ends"] = _dates(c)

    # open ends: only member contributions in scope (drops non-member/moderator rows and empty responses)
    if "open_ends" in f:
        o = f["open_ends"]
        if "IsNonMemberRole" in o:
            o = o[o["IsNonMemberRole"].fillna(0) != 1]
        o = restrict(o).drop(columns=["IsNonMemberRole"], errors="ignore")
        o = o[o["Response"].notna()]
        f["open_ends"] = _dates(o)

    return f
