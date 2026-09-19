from alert_explanation.service import explain_alert

def explain_incident(runtime, decision_id):
    incident = runtime.incidents.get(decision_id)
    if not incident:
        raise KeyError(decision_id)
    decision = incident['decision']
    record = incident['record']
    mid = decision.machine_id
    prediction = incident['prediction']
    source = dict(status='available',machine_id=mid,reported_at=record['timestamp'])
    observations = [dict(id='controller-state',signal='Controller status',
        description='Controller reported '+record['status']+'.')]
    units = {'current':'A','temperature':'°C','vibration':'mm/s RMS','rpm':'rpm'}
    for key,value in (record.get('sensors') or {}).items():
        observations.append(dict(id='signal-'+key,signal=key,value=value,unit=units[key]))
    twin = runtime.twin.get_machine_snapshot(mid)
    twin_source = dict(status='stale' if twin['stale'] else 'available',
        machine_id=mid,reported_at=twin['last_updated'])
    recovery_source = dict(status='available',machine_id=mid,reported_at=runtime.clock().isoformat())
    recovery = dict(**recovery_source,
        human=dict(id='human-assessment',correction_possible='unknown',quick_correction='unknown'),
        delay_consequences=[dict(id='timeout-policy',description=
            'After '+str(runtime.settings.correction_seconds)+' seconds, the rule-based scheduler evaluates configured compatible, available machines and compares simulated throughput.')],
        alternatives=[],scenarios=[])
    sid = decision.whatif_scenario_id
    comparison = runtime.comparisons.get(sid)
    if comparison:
        for key,name in [('baseline','Wait for correction'),('recovery','Use testing standby')]:
            result = comparison.get(key)
            if result is not None:
                recovery['scenarios'].append(dict(id=key,name=name,
                    throughput=result['throughput_units_per_hour'],throughput_unit='finished boards/hour',
                    horizon_minutes=comparison['horizon_minutes'],starting_state_id=comparison['starting_state_id'],
                    output_scope='complete PCB assembly line',assumptions=comparison['assumptions']))
        recovery['baseline_scenario_id']='baseline'
        if comparison.get('recovery'):
            recovery['recovery_scenario_id']='recovery'
            recovery['alternatives'].append(dict(id='alternate',machine_id='M4-BACKUP',
                machine_name='Testing standby (simulated)',compatibility='confirmed',available=True,
                allocation_status='executed' if decision.status.value=='reallocated' else 'proposed',
                reason='Configured demo testing standby; availability was checked at the recovery decision.'))
    inputs = dict(alert=dict(id=decision_id,machine_id=mid,
        machine_name=runtime.config.get(mid).name,occurred_at=record['timestamp'],severity='warning'),
        data_acquisition=dict(**source,observations=observations),
        digital_twin=dict(**twin_source,impacts=[
            dict(id='capacity',description='Estimated effective capacity: '+str(twin['effective_capacity_units_per_hour'])+' boards/hour.'),
            dict(id='queue',description='Current input queue: '+str(twin['queue_length'])+' boards.'),
            dict(id='outcome',description='Recovery state: '+decision.status.value.replace('_',' ')+
                 '. This is virtual routing only; no hardware commands are issued.')]),
        decision_recovery=recovery)
    if prediction:
        inputs['ann_fault_detection']=dict(**source,model_name='MLPClassifier (synthetic training)',
            anomalies=[dict(id='ann-classification',label='Suspected '+prediction['fault_type'].replace('_',' ').lower(),
                confidence_score=prediction['confidence'],
                description='Current-fault classification; it does not establish the root cause or predict future failure.')],
            suspected_causes=[])
    result = explain_alert(inputs).model_dump(mode='json')
    result['warnings'].append('Root cause and repair duration are not established by the provided inputs.')
    if runtime.settings.mode=='demo':
        result['warnings'].append('Demo data and any standby allocation are simulated.')
    return result

