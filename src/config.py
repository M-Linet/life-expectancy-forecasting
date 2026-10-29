"""Paths, API endpoints and indicator codes."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

PANEL_PATH = PROCESSED_DIR / "life_expectancy_panel.csv"
GHO_API = "https://ghoapi.azureedge.net/api"
WORLD_BANK_API = "https://api.worldbank.org/v2"

START_YEAR = 1990
END_YEAR = 2025

# Both are published by sex: both sexes, female, male.
GHO_INDICATORS = {
    "WHOSIS_000001": "life_expectancy",  # Life expectancy at birth (years)
    "WHOSIS_000002": "hale",             # Healthy life expectancy (HALE) at birth (years)
}

# no mortality rates here: LE is calculated from them (leakage)
WB_INDICATORS = {
    "NY.GDP.PCAP.PP.KD": "gdp_pc_ppp",            # GDP per capita, PPP (constant intl $)
    "SH.XPD.CHEX.GD.ZS": "health_exp_pct_gdp",    # Current health expenditure (% of GDP)
    "SH.XPD.CHEX.PC.CD": "health_exp_pc_usd",     # Current health expenditure per capita (US$)
    "SH.IMM.IDPT": "dtp3_coverage",               # DTP3 immunization (% of children 12-23 months)
    "SH.IMM.MEAS": "measles_coverage",            # Measles immunization (% of children 12-23 months)
    "SH.DYN.AIDS.ZS": "hiv_prevalence",           # HIV prevalence (% of population 15-49)
    "SE.SEC.ENRR": "secondary_enrollment",        # School enrollment, secondary (% gross)
    "SH.H2O.BASW.ZS": "basic_water",              # People using at least basic drinking water (%)
    "SH.STA.BASS.ZS": "basic_sanitation",         # People using at least basic sanitation (%)
    "SN.ITK.DEFC.ZS": "undernourishment",         # Prevalence of undernourishment (%)
    "SP.URB.TOTL.IN.ZS": "urban_pct",             # Urban population (% of total)
    "SP.POP.TOTL": "population",                  # Population, total (used for weighting)
}

# used in notebooks 02 and 04 only, never as predictors
WB_MORTALITY = {
    "SH.DYN.MORT": "u5_mortality",                # Under-5 mortality rate (per 1,000 live births)
    "SH.DYN.NMRT": "neonatal_mortality",          # Neonatal mortality rate (per 1,000 live births)
    "SH.STA.MMRT": "maternal_mortality_ratio",    # Maternal deaths per 100,000 live births (modelled)
    "SP.DYN.AMRT.FE": "adult_mortality_female",   # Prob. of dying 15-60, female (per 1,000)
    "SP.DYN.AMRT.MA": "adult_mortality_male",     # Prob. of dying 15-60, male (per 1,000)
    "SH.DYN.NCOM.ZS": "ncd_mortality_30_70",      # Prob. of dying 30-70 from CVD, cancer, diabetes, CRD (%)
    "SH.HIV.INCD.ZS": "hiv_incidence",            # New HIV infections per 1,000 uninfected (15-49)
    "SH.TBS.INCD": "tb_incidence",                # TB incidence per 100,000 people
    "SH.MLR.INCD.P3": "malaria_incidence",        # Malaria cases per 1,000 population at risk
    "SH.STA.TRAF.P5": "road_traffic_deaths",      # Road traffic deaths per 100,000 people
    "SH.STA.SUIC.P5": "suicide_rate",             # Suicide deaths per 100,000 people
    "SH.DTH.COMM.ZS": "deaths_communicable_pct",  # Communicable, maternal, perinatal, nutritional (% of deaths)
    "SH.DTH.NCOM.ZS": "deaths_ncd_pct",           # Non-communicable diseases (% of deaths)
    "SH.DTH.INJR.ZS": "deaths_injury_pct",        # Injuries (% of deaths)
}

# nMx by country, year, sex. Code looked up from the GHO catalogue by name.
LIFE_TABLE_NAME_PATTERN = r"^\s*nMx\b"
LIFE_TABLES_PATH = PROCESSED_DIR / "life_tables.csv"

AGE_BANDS = [(0, 1, "Infants (<1)"), (1, 5, "Children 1-4"), (5, 15, "5-14"), (15, 30, "15-29"),
             (30, 50, "30-49"), (50, 70, "50-69"), (70, 200, "70+")]

# GHO sex codes (old and new forms)
SEX_CODES = {
    "SEX_BTSX": "both", "BTSX": "both",
    "SEX_FMLE": "female", "FMLE": "female",
    "SEX_MLE": "male", "MLE": "male",
}
