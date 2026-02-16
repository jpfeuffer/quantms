process SPECTRONAUT_PULSAR_STEP1 {
    tag "${meta.experiment_id}_batch${meta.batch_id}"
    label 'process_medium'
    label 'spectronaut'

    input:
    tuple val(meta), path(raw_files)
    path fasta

    output:
    tuple val(meta), path('*.psar'), emit: search_archive
    path 'versions.yml', emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def experimentName = meta.experiment_id ?: 'spectronaut'
    def batchId = meta.batch_id ?: 0
    def rawArgs = raw_files.collect { "-r ${it}" }.join(' ')
    def fastaArgs = fasta.collect { "-fasta ${it}" }.join(' ')
    def settingsPropArgs = params.spectronaut_settings_prop ? "-rs ${params.spectronaut_settings_prop}" : ''
    def settingsJsonArgs = params.spectronaut_settings_json ? "-j ${params.spectronaut_settings_json}" : ''
    def archiveName = "search_archive_step1_batch${batchId}.psar"
    """
    # Activate license if key provided via environment variable
    if [ -n "\${SPECTRONAUT_LICENSE_KEY:-}" ]; then
        echo "Activating Spectronaut floating license..."
        spectronaut activate "\$SPECTRONAUT_LICENSE_KEY"
    fi
    
    spectronaut lg -se Pulsar \\
        ${rawArgs} \\
        ${fastaArgs} \\
        -a ${archiveName} \\
        -o . \\
        ${settingsPropArgs} \\
        ${settingsJsonArgs} \\
        --pulsarStage pulsarStep1

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: \\$(spectronaut -h 2>&1 | head -n 1 | sed 's/^[[:space:]]*//')
    END_VERSIONS
    """

    stub:
    def batchId = meta.batch_id ?: 0
    def archiveName = "search_archive_step1_batch${batchId}.psar"
    """
    touch ${archiveName}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: stub
    END_VERSIONS
    """
}
