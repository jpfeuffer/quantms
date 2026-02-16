process SPECTRONAUT_DIA_ANALYSIS {
    tag "${meta.experiment_id}_batch${meta.batch_id}"
    label 'process_medium'
    label 'spectronaut'

    input:
    tuple val(meta), path(raw_files)
    path library
    path expdesign

    output:
    tuple val(meta), path('**/*.sne'), emit: sne_file
    path 'versions.yml', emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def experimentName = meta.experiment_id ?: 'spectronaut'
    def batchId = meta.batch_id ?: 0
    def rawArgs = raw_files.collect { "-r ${it}" }.join(' ')
    def settingsPropArgs = params.spectronaut_settings_prop ? "-s ${params.spectronaut_settings_prop}" : ''
    def settingsJsonArgs = params.spectronaut_settings_json ? "-j ${params.spectronaut_settings_json}" : ''
    def conditionArgs = expdesign ? "-con ${expdesign}" : ''
    """
    # Activate license if key provided via environment variable
    if [ -n "\${SPECTRONAUT_LICENSE_KEY:-}" ]; then
        echo "Activating Spectronaut floating license..."
        spectronaut activate "\$SPECTRONAUT_LICENSE_KEY"
    fi
    
    spectronaut diaanalysis \\
        -o . \\
        -a ${library} \\
        ${rawArgs} \\
        -n "${experimentName}_batch${batchId}" \\
        ${settingsPropArgs} \\
        ${settingsJsonArgs} \\
        ${conditionArgs}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: \\$(spectronaut -h 2>&1 | head -n 1 | sed 's/^[[:space:]]*//')
    END_VERSIONS
    """

    stub:
    def experimentName = meta.experiment_id ?: 'spectronaut'
    def batchId = meta.batch_id ?: 0
    """
    mkdir -p stub_output
    touch stub_output/${experimentName}_batch${batchId}.sne

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: stub
    END_VERSIONS
    """
}
