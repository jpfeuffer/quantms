process SPECTRONAUT_SNE_MERGE {
    tag "${experimentName}"
    label 'process_high'
    label 'spectronaut'

    input:
    val experimentName
    path sne_files
    path fasta
    path expdesign

    output:
    path '*Report*.tsv', emit: report
    path '*.sne', emit: sne_file, optional: true
    path 'versions.yml', emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def sneArgs = sne_files.collect { "-sne ${it}" }.join(' ')
    def fastaArgs = fasta.collect { "-fasta ${it}" }.join(' ')
    def settingsPropArgs = params.spectronaut_settings_prop ? "-s ${params.spectronaut_settings_prop}" : ''
    def settingsJsonArgs = params.spectronaut_settings_json ? "-j ${params.spectronaut_settings_json}" : ''
    def conditionArgs = expdesign ? "-con ${expdesign}" : ''
    def numSamples = sne_files.size()
    
    // Activate license before running merge
    def licenseActivation = '''
    # Activate license if key provided via environment variable
    if [ -n "${SPECTRONAUT_LICENSE_KEY:-}" ]; then
        echo "Activating Spectronaut floating license..."
        spectronaut activate "$SPECTRONAUT_LICENSE_KEY"
    fi
    '''
    
    // Use combine for large experiments (>500 samples), manageSNE --merge for smaller
    if (numSamples > 500) {
        """
        ${licenseActivation}
        
        spectronaut combine \\
            -o . \\
            ${sneArgs} \\
            ${fastaArgs} \\
            ${settingsPropArgs} \\
            ${settingsJsonArgs}

        cat <<-END_VERSIONS > versions.yml
        "${task.process}":
            spectronaut: \\$(spectronaut -h 2>&1 | head -n 1 | sed 's/^[[:space:]]*//')
        END_VERSIONS
        """
    } else {
        """
        ${licenseActivation}
        
        spectronaut manageSNE --merge \\
            -o . \\
            ${sneArgs} \\
            ${settingsPropArgs} \\
            ${settingsJsonArgs} \\
            ${conditionArgs}

        cat <<-END_VERSIONS > versions.yml
        "${task.process}":
            spectronaut: \\$(spectronaut -h 2>&1 | head -n 1 | sed 's/^[[:space:]]*//')
        END_VERSIONS
        """
    }

    stub:
    """
    touch ${experimentName}_Report_BGS_Factory_Report.tsv
    touch ${experimentName}.sne

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        spectronaut: stub
    END_VERSIONS
    """
}
