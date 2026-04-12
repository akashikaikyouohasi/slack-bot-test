import time
import boto3
from strands import tool

logs_client = boto3.client("logs")


@tool
def list_log_groups(prefix: str = "") -> str:
    """CloudWatch Logsのロググループ一覧を取得する。

    Args:
        prefix: ロググループ名のプレフィックスでフィルタ。例: "/aws/lambda/"
    """
    kwargs = {}
    if prefix:
        kwargs["logGroupNamePrefix"] = prefix

    groups = []
    paginator = logs_client.get_paginator("describe_log_groups")
    for page in paginator.paginate(**kwargs):
        for group in page["logGroups"]:
            groups.append(group["logGroupName"])

    if not groups:
        return "ロググループが見つかりませんでした。"

    return "\n".join(groups)


@tool
def search_logs(log_group_name: str, query: str = "", hours_ago: int = 1) -> str:
    """CloudWatch Logs Insightsでログを検索する。

    Args:
        log_group_name: 検索対象のロググループ名
        query: Logs Insightsのクエリ文。空の場合はERRORログを検索する
        hours_ago: 何時間前から検索するか（デフォルト: 1時間）
    """
    if not query:
        query = (
            "fields @timestamp, @message, @logStream "
            "| filter @message like /(?i)error/ "
            "| sort @timestamp desc "
            "| limit 20"
        )

    end_time = int(time.time())
    start_time = end_time - (hours_ago * 3600)

    response = logs_client.start_query(
        logGroupName=log_group_name,
        startTime=start_time,
        endTime=end_time,
        queryString=query,
    )
    query_id = response["queryId"]

    # クエリ完了を待つ（最大30秒）
    for _ in range(30):
        result = logs_client.get_query_results(queryId=query_id)
        if result["status"] == "Complete":
            break
        time.sleep(1)

    if not result["results"]:
        return "該当するログは見つかりませんでした。"

    lines = []
    for row in result["results"]:
        fields = {f["field"]: f["value"] for f in row}
        lines.append(
            f"[{fields.get('@timestamp', '')}] {fields.get('@message', '').strip()}"
        )

    return "\n---\n".join(lines)
