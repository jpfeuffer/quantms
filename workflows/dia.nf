/*
========================================================================================
    IMPORT LOCAL MODULES/SUBWORKFLOWS
========================================================================================
*/

//
// MODULES: Local to the pipeline
//
include { GENERATE_CFG                } from '../modules/local/diann/generate_cfg/main'
include { CONVERT_RESULTS             } from '../modules/local/diann/convert_results/main'
include { MSSTATS_LFQ                 } from '../modules/local/msstats/msstats_lfq/main'
include { PRELIMINARY_ANALYSIS        } from '../modules/local/diann/preliminary_analysis/main'
include { ASSEMBLE_EMPIRICAL_LIBRARY  } from '../modules/local/diann/assemble_empirical_library/main'
include { INSILICO_LIBRARY_GENERATION } from '../modules/local/diann/insilico_library_generation/main'
include { INDIVIDUAL_ANALYSIS         } from '../modules/local/diann/individual_analysis/main'
include { FINAL_QUANTIFICATION        } from '../modules/local/diann/final_quantification/main'
include { SPECTRONAUT_PULSAR_STEP1    } from '../modules/local/spectronaut/pulsar_step1/main'
include { SPECTRONAUT_PULSAR_STEP2    } from '../modules/local/spectronaut/pulsar_step2/main'
include { SPECTRONAUT_PULSAR_STEP3    } from '../modules/local/spectronaut/pulsar_step3/main'
include { SPECTRONAUT_LIBRARY_MERGE   } from '../modules/local/spectronaut/library_merge/main'
include { SPECTRONAUT_DIA_ANALYSIS    } from '../modules/local/spectronaut/dia_analysis/main'
include { SPECTRONAUT_SNE_MERGE       } from '../modules/local/spectronaut/sne_merge/main'

//
// SUBWORKFLOWS: Consisting of a mix of local and nf-core/modules
//

/*
========================================================================================
    RUN MAIN WORKFLOW
========================================================================================
*/

workflow DIA {
    take:
    ch_file_preparation_results
    ch_expdesign
    ch_ms_info

    main:

    ch_software_versions = channel.empty()
    ch_diann_report = channel.empty()
    ch_diann_report_parquet = channel.empty()
    ch_msstats_in = channel.empty()
    ch_out_triqler = channel.empty()
    ch_final_result = channel.empty()
    ch_msstats_out = channel.empty()

    if (params.dia_tool == 'spectronaut') {
        // Spectronaut distributed workflow (6 steps)
        channel.fromPath(params.database).set { ch_searchdb }

        // Step 1: Split files into batches for parallelization
        ch_file_preparation_results
            .map { result -> [result[0], result[1]] }
            .toSortedList { a, b -> file(a[1]).getName() <=> file(b[1]).getName() }
            .flatMap()
            .collate(params.spectronaut_batch_size)
            .map { batch ->
                def batch_id = batch[0].hashCode().abs() % 100000
                def meta = [experiment_id: params.outdir.split('/')[-1], batch_id: batch_id]
                def raw_files = batch.collect { it[1] }
                [meta, raw_files]
            }
            .set { ch_batched_files }

        // Step 1.1: Pulsar Step 1 (parallelized - mapping pipeline)
        SPECTRONAUT_PULSAR_STEP1(ch_batched_files, ch_searchdb)
        ch_software_versions = ch_software_versions.mix(SPECTRONAUT_PULSAR_STEP1.out.versions)

        // Step 1.2: Pulsar Step 2 (reduce - generate .qsp)
        SPECTRONAUT_PULSAR_STEP2(
            params.outdir.split('/')[-1],
            SPECTRONAUT_PULSAR_STEP1.out.search_archive.collect { it[1] }
        )
        ch_software_versions = ch_software_versions.mix(SPECTRONAUT_PULSAR_STEP2.out.versions)

        // Step 1.3: Pulsar Step 3 (parallelized - mapping pipeline with .qsp)
        // Combine batched files with their step1 archives
        ch_batched_files
            .join(SPECTRONAUT_PULSAR_STEP1.out.search_archive, by: 0)
            .set { ch_step3_input }

        SPECTRONAUT_PULSAR_STEP3(ch_step3_input, SPECTRONAUT_PULSAR_STEP2.out.qsp_file)
        ch_software_versions = ch_software_versions.mix(SPECTRONAUT_PULSAR_STEP3.out.versions)

        // Step 1.4: Merge archives to library (reduce)
        SPECTRONAUT_LIBRARY_MERGE(
            params.outdir.split('/')[-1],
            SPECTRONAUT_PULSAR_STEP3.out.search_archive.collect { it[1] }
        )
        ch_software_versions = ch_software_versions.mix(SPECTRONAUT_LIBRARY_MERGE.out.versions)

        // Step 2.1: DIA analysis per batch (parallelized - mapping pipeline)
        ch_batched_files
            .map { meta, raw_files -> [meta, raw_files] }
            .set { ch_dia_input }

        SPECTRONAUT_DIA_ANALYSIS(
            ch_dia_input,
            SPECTRONAUT_LIBRARY_MERGE.out.library,
            ch_expdesign
        )
        ch_software_versions = ch_software_versions.mix(SPECTRONAUT_DIA_ANALYSIS.out.versions)

        // Step 2.2: Merge SNE files and generate final report (reduce)
        SPECTRONAUT_SNE_MERGE(
            params.outdir.split('/')[-1],
            SPECTRONAUT_DIA_ANALYSIS.out.sne_file.collect { it[1] },
            ch_searchdb,
            ch_expdesign
        )
        ch_software_versions = ch_software_versions.mix(SPECTRONAUT_SNE_MERGE.out.versions)

        // TODO: Convert Spectronaut report to standard format for downstream processing
        // For now, just pass through the report
        ch_diann_report = SPECTRONAUT_SNE_MERGE.out.report
        ch_diann_report_parquet = channel.empty()  // Spectronaut doesn't produce parquet
        ch_msstats_in = channel.empty()  // TODO: Convert report format
        ch_final_result = SPECTRONAUT_SNE_MERGE.out.report
    } else {
        channel.fromPath(params.database).set { ch_searchdb }

        ch_file_preparation_results.multiMap {
            result ->
            meta:   preprocessed_meta(result[0])
            ms_file:result[1]
        }.set { ch_result }

        meta = ch_result.meta.unique { m -> m[0] }

        GENERATE_CFG(meta)
        ch_software_versions = ch_software_versions
            .mix(GENERATE_CFG.out.versions)

        //
        // MODULE: SILICOLIBRARYGENERATION
        //
        if (params.diann_speclib != null && params.diann_speclib.toString() != "") {
            speclib = channel.from(file(params.diann_speclib, checkIfExists: true))
        } else {
            INSILICO_LIBRARY_GENERATION(ch_searchdb, GENERATE_CFG.out.diann_cfg)
            speclib = INSILICO_LIBRARY_GENERATION.out.predict_speclib
        }

        if (params.skip_preliminary_analysis) {
            assembly_log = channel.fromPath(params.empirical_assembly_log)
            empirical_library = channel.fromPath(params.diann_speclib)
            indiv_fin_analysis_in = ch_file_preparation_results.combine(ch_searchdb)
                .combine(assembly_log)
                .combine(empirical_library)
            empirical_lib = empirical_library
        } else {
            //
            // MODULE: PRELIMINARY_ANALYSIS
            //
            if (params.random_preanalysis) {
                preanalysis_subset = ch_file_preparation_results
                    .toSortedList{ a, b -> file(a[1]).getName() <=> file(b[1]).getName() }
                    .flatMap()
                    .randomSample(params.empirical_assembly_ms_n, params.random_preanalysis_seed)
                empirical_lib_files = preanalysis_subset
                    .map { result -> result[1] }
                    .collect( sort: { a, b -> file(a).getName() <=> file(b).getName() } )
                PRELIMINARY_ANALYSIS(preanalysis_subset.combine(speclib))
            } else {
                empirical_lib_files = ch_file_preparation_results
                    .map { result -> result[1] }
                    .collect( sort: { a, b -> file(a).getName() <=> file(b).getName() } )
                PRELIMINARY_ANALYSIS(ch_file_preparation_results.combine(speclib))
            }
            ch_software_versions = ch_software_versions
                .mix(PRELIMINARY_ANALYSIS.out.versions)

            //
            // MODULE: ASSEMBLE_EMPIRICAL_LIBRARY
            //
            // Order matters in DIANN, This should be sorted for reproducible results.
            ASSEMBLE_EMPIRICAL_LIBRARY(
                empirical_lib_files,
                meta,
                PRELIMINARY_ANALYSIS.out.diann_quant.collect(),
                speclib
            )
            ch_software_versions = ch_software_versions
                .mix(ASSEMBLE_EMPIRICAL_LIBRARY.out.versions)
            indiv_fin_analysis_in = ch_file_preparation_results
                .combine(ch_searchdb)
                .combine(ASSEMBLE_EMPIRICAL_LIBRARY.out.log)
                .combine(ASSEMBLE_EMPIRICAL_LIBRARY.out.empirical_library)

            empirical_lib = ASSEMBLE_EMPIRICAL_LIBRARY.out.empirical_library
        }

        //
        // MODULE: INDIVIDUAL_ANALYSIS
        //
        INDIVIDUAL_ANALYSIS(indiv_fin_analysis_in)
        ch_software_versions = ch_software_versions
            .mix(INDIVIDUAL_ANALYSIS.out.versions)

        //
        // MODULE: DIANNSUMMARY
        //
        // Order matters in DIANN, This should be sorted for reproducible results.
        // NOTE: ch_results.ms_file contains the name of the ms file, not the path.
        // The next step only needs the name (since it uses the cached .quant)
        // Converting to a file object and using its name is necessary because ch_result.ms_file contains
        // locally, evey element in ch_result is a string, whilst on cloud it is a path.
        ch_result
            .ms_file.map { msfile -> file(msfile).getName() }
            .collect(sort: true)
            .set { ms_file_names }

        FINAL_QUANTIFICATION(
            ms_file_names,
            meta,
            empirical_lib,
            INDIVIDUAL_ANALYSIS.out.diann_quant.collect(),
            ch_searchdb)

        ch_software_versions = ch_software_versions.mix(
            FINAL_QUANTIFICATION.out.versions
        )

        //
        // MODULE: DIANNCONVERT
        //
        diann_main_report = FINAL_QUANTIFICATION.out.main_report.mix(FINAL_QUANTIFICATION.out.report_parquet).last()

        CONVERT_RESULTS(
            diann_main_report, ch_expdesign,
            FINAL_QUANTIFICATION.out.pg_matrix,
            FINAL_QUANTIFICATION.out.pr_matrix, ch_ms_info,
            meta,
            ch_searchdb,
            FINAL_QUANTIFICATION.out.versions
        )
        ch_software_versions = ch_software_versions
            .mix(CONVERT_RESULTS.out.versions)

        //
        // MODULE: MSSTATS
        if (!params.skip_post_msstats) {
            MSSTATS_LFQ(CONVERT_RESULTS.out.out_msstats)
            ch_msstats_out = MSSTATS_LFQ.out.msstats_csv
            ch_software_versions = ch_software_versions.mix(
                MSSTATS_LFQ.out.versions
            )
        }

        ch_diann_report = FINAL_QUANTIFICATION.out.main_report
        ch_diann_report_parquet = FINAL_QUANTIFICATION.out.report_parquet
        ch_msstats_in = CONVERT_RESULTS.out.out_msstats
        ch_out_triqler = CONVERT_RESULTS.out.out_triqler
        ch_final_result = CONVERT_RESULTS.out.out_mztab
    }

    emit:
    versions                = ch_software_versions
    diann_report            = ch_diann_report
    diann_report_parquet    = ch_diann_report_parquet
    msstats_in              = ch_msstats_in
    out_triqler             = ch_out_triqler
    final_result            = ch_final_result
    msstats_out             = ch_msstats_out
}

// remove meta.id to make sure cache identical HashCode
def preprocessed_meta(LinkedHashMap meta) {
    def parameters = [:]
    parameters['experiment_id']                 = meta.experiment_id
    parameters['acquisition_method']            = meta.acquisition_method
    parameters['dissociationmethod']            = meta.dissociationmethod
    parameters['labelling_type']                = meta.labelling_type
    parameters['fixedmodifications']            = meta.fixedmodifications
    parameters['variablemodifications']         = meta.variablemodifications
    parameters['precursormasstolerance']        = meta.precursormasstolerance
    parameters['precursormasstoleranceunit']    = meta.precursormasstoleranceunit
    parameters['fragmentmasstolerance']         = meta.fragmentmasstolerance
    parameters['fragmentmasstoleranceunit']     = meta.fragmentmasstoleranceunit
    parameters['enzyme']                        = meta.enzyme

    return parameters
}

/*
========================================================================================
    THE END
========================================================================================
*/
