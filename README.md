# splunk-forwarder
A custom search command to metricize Splunk logs and send to SignalFx


### Setup
1. The sfxforwarder app needs to be installed on the search head. App installation process
   is identical to any other app (may vary depending on Splunk Cloud vs on-premise
   deployment).

2. After installation you will be prompted by a setup screen. Enter your access token 
   and your ingest URL, if not in the US0 realm.

3. You can now use the custom search commands "tosfx" and "streamtosfx"

**Note** Setup can be re-ran via "Manage apps" and selecting "set up" for the app.

### Features

#### Custom Search Commands

**streamtosfx**: Send datapoints to SignalFx as soon as they’re retrieved.
                 Fields marked using the macros listed below will be used as metric names. If
                 the field _time is available, it will be used. If not the current timestamp is used.
                 The rest of the fields are treated as dimensions. Works best with realtime mode.

**tosfx**:       Send the datapoints to SignalFx in a non streaming manner.
                 Does not work in realtime mode, but has higher throughput.

#### Macros

**gauge(1)**:   Mark the field as type gauge

**counter(1)**: Mark the field as type counter

**cumulative_counter(1)**: Mark the field as type cumulative counter


#### Examples


```
index=_internal group=per_index_thruput series!=_* | rename ev AS eventCount | rename kb AS kilobytes | table _time kilobytes eventCountindexName | `gauge(kilobytes)` |`gauge(eventCount)` | streamtosfx
```

```
index=_internal group=per_index_thruput series!=_*          Look in the internal index to get the per index throughput. Filter out internal indexes.
| rename ev AS eventCount | rename kb AS kilobytes          Rename the fields to something more human readable
| table _time kilobytes eventCount indexName                Select just the fields _time, kilobytes, eventCount, and indexName
| `gauge(kilobytes)` | `gauge(eventCount)`                  Mark kilobytes and eventcount as metric fields of the type gauge
| tosfx                                                     Send the datapoints to SignalFx
```
