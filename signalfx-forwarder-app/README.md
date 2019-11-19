# signalfx-forwarder

A custom search command to metricize Splunk events and send them to SignalFx

### Setup
1. The signalfx-forwarder-app app needs to be installed on the search head. App
   installation process is identical to any other app (may vary depending on
   Splunk Cloud vs on-premise deployment).

2. After installation you will be prompted by a setup screen. Enter your access
   token and your ingest URL, if not in the US0 realm.  The form of the URL is
   `https://ingest.<YOUR_REALM>.signalfx.com`.

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

Both commands also support arguments `dryrun` and `debug`.
- `dryrun=t` will result in not sending any metrics to SignalFx, which is useful for
testing your potential output in Splunk.
- `debug=t` will log both your access token and the ingest url.

These arguments can be appended to the new commands. For example, `tosfx debug=t dryrun=t`

#### Macros

**gauge(1)**:   Mark the field as type gauge

**counter(1)**: Mark the field as type counter

**cumulative_counter(1)**: Mark the field as type cumulative counter


#### Examples

```
index=_internal group=per_index_thruput series!=_* | rename ev AS eventCount | rename kb AS kilobytes | table _time kilobytes eventCount series host | `gauge(kilobytes)` |`gauge(eventCount)` | tosfx
```

```
index=_internal group=per_index_thruput series!=_*          Look in the internal index to get the per index throughput. Filter out internal indexes.
| rename ev AS eventCount | rename kb AS kilobytes          Rename the fields to something more human readable
| table _time kilobytes eventCount series host              Select the fields _time, kilobytes, eventCount, series, and host
| `gauge(kilobytes)` | `gauge(eventCount)`                  Mark kilobytes and eventcount as metric fields of the type gauge
| tosfx                                                     Send the datapoints to SignalFx
```

When selecting fields, any fields not marked to be convereted to a SignalFx metric will turn into a dimension.
If you do not select the `_time` field, SignalFx will add the timestamp when the metric is received.

### Support

To file a bug report or request help please file an issue on our [Github
repository](https://github.com/signalfx/splunk-forwarder/) for this app.
