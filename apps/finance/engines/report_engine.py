class ReportEngine:

    @staticmethod
    def summary(data):
        return {
            "Revenue": data.get("gmv_fee"),
            "Net Revenue": data.get("gmv_net_after_tax"),
            "Sale": data.get("sale_commission"),
            "Team": data.get("team_bonus"),
            "Company": data.get("company_profit"),
        }