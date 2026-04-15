//
// Check input YAML and stage the file
//

workflow INPUT_CHECK {
    take:
    input_file

    main:

    ch_software_versions = channel.empty()

    // Stage the YAML input file and pass it through
    emit:
    ch_input_file   = input_file
    versions        = ch_software_versions
}
