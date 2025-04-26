function process_mesh_files_new(mesh_dir)
    if nargin < 1
        error('You must provide the path to the mesh directory as an argument.');
    end

    % Ensure mesh_dir is valid
    if ~isfolder(mesh_dir)
        error('The specified mesh directory does not exist.');
    end

    mesh_files = dir(fullfile(mesh_dir, '*.msh'));

    results_dir = fullfile(mesh_dir, 'results');
    if ~exist(results_dir, 'dir')
        mkdir(results_dir);
    end

    summary_file = fullfile(results_dir, 'summary.txt');
    summary_fid = fopen(summary_file, 'w');
    if summary_fid == -1
        error('Cannot open summary file for writing.');
    end

    csv_file = fullfile(results_dir, 'summary.csv');
    csv_data = {};  % Initialize cell array to store CSV data

    warning('off', 'all');

    for i = 1:length(mesh_files)
        mesh_file = fullfile(mesh_dir, mesh_files(i).name);
        fprintf('Processing %s\n', mesh_files(i).name);
        m = mesh_load_gmsh4(mesh_file);

        fig_histogram = figure('Visible', 'off');
        ax_histogram = axes(fig_histogram);
        mesh_get_histogram(m, 'haxis', ax_histogram);
        save_histogram_image(mesh_files(i).name, fig_histogram, results_dir);
        close(fig_histogram);

        s = mesh_get_fieldpeaks_and_focality(m, 'printsummary', false);
        save_results(mesh_files(i).name, s, results_dir);
        write_summary(summary_fid, mesh_files(i).name, s);

        % Collect data for CSV
        csv_row = {mesh_files(i).name, s.field_name, num2str(s.region_idx), s.max, ...
            s.perc_values(1), s.perc_values(2), s.perc_values(3), ...
            s.focality_values(1) / 1000, s.focality_values(2) / 1000, s.focality_values(3) / 1000, s.focality_values(4) / 1000, ...
            mat2str(s.XYZ_max), ...
            mat2str(s.XYZ_perc(1,:)), mat2str(s.XYZ_perc(2,:)), mat2str(s.XYZ_perc(3,:)), ...
            mat2str(s.XYZstd_perc(1,:)), mat2str(s.XYZstd_perc(2,:)), mat2str(s.XYZstd_perc(3,:))};        
        csv_data = [csv_data; csv_row];
    end

    fclose(summary_fid);
    warning('on', 'all');

    % Create table and write to CSV
    csv_table = cell2table(csv_data, 'VariableNames', create_variable_names());
    writetable(csv_table, csv_file);
end

function save_results(filename, s, results_dir)
    [~, name, ~] = fileparts(filename);
    peaks_focality_file = fullfile(results_dir, [name, '_peaks_focality.mat']);
    save(peaks_focality_file, 's');
end

function save_histogram_image(filename, fig, results_dir)
    [~, name, ~] = fileparts(filename);
    histogram_image_file = fullfile(results_dir, [name, '_histogram.png']);
    saveas(fig, histogram_image_file);
end

function write_summary(fid, filename, s)
    fprintf(fid, 'Summary for %s\n', filename);
    fprintf(fid, 'Field Name: %s\n', s.field_name);
    fprintf(fid, 'Region Indices: %s\n', num2str(s.region_idx));
    fprintf(fid, 'Max Value: %f V/m\n', s.max);
    fprintf(fid, 'Percentiles: %s\n', num2str(s.percentiles));
    fprintf(fid, 'Percentile Values: %s V/m\n', num2str(s.perc_values));
    fprintf(fid, 'Focality Cutoffs: %s\n', num2str(s.focality_cutoffs));
    focality_values_cm3 = s.focality_values / 1000;
    fprintf(fid, 'Focality Values: %s (in cubic cm)\n', num2str(focality_values_cm3));
    fprintf(fid, 'XYZ Max: %s\n', mat2str(s.XYZ_max));
    fprintf(fid, 'XYZ Percentiles: %s\n', mat2str(s.XYZ_perc));
    fprintf(fid, 'XYZ Std Percentiles: %s\n', mat2str(s.XYZstd_perc));

    fprintf(fid, '---------------------------------------------\n\n');
end

function var_names = create_variable_names()
    var_names = {'FileName', 'FieldName', 'RegionIndices', 'MaxValue', ...
                 'PercentileValue_95', 'PercentileValue_99', 'PercentileValue_99.9', ...
                 'FocalityValue_50', 'FocalityValue_75', 'FocalityValue_90', 'FocalityValue_95', ...
                 'XYZ_Max', ...
                 'XYZ_Percentiles_95', 'XYZ_Percentiles_99', 'XYZ_Percentiles_99.9', ...
                 'XYZ_Std_Percentiles_95', 'XYZ_Std_Percentiles_99', 'XYZ_Std_Percentiles_99.9'};
end
