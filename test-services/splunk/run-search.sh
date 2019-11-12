#!/bin/bash

set -euxo pipefail

SFX_CMD=${SFX_CMD:-tosfx}
QUERY='index=_internal group=per_index_thruput series!=_* | rename ev AS eventCount | rename kb AS kilobytes | table _time kilobytes eventCount series host | `gauge(kilobytes)` | `gauge(eventCount)`'

/opt/splunk/bin/splunk list user -auth admin:testing123
/opt/splunk/bin/splunk search """$QUERY | $SFX_CMD"""
