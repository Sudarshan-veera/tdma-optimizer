function tdma_sim(varargin)
%TDMA_SIM  Schedule-driven TDMA simulation for the TDMA Schedule Planner and Optimizer.
%
%   tdma_sim                      16-node demo grid, MATLAB computes its own schedule
%   tdma_sim('Csv','schedule_sim.csv')
%                                 use the coordinates and the Python Brain's schedule
%                                 from the CSV made by sim/export_for_sims.py
%   Name-value options:
%     'Csv'     path to schedule_sim.csv ('' = built-in 4x4 grid, 300 m spacing)
%     'Range'   radio range in metres (default 500)
%     'SlotMs'  slot duration in ms (default 1)
%     'Random'  number of random schedules to average (default 200)
%     'Plots'   true/false, draw and save figures (default true)
%     'OutDir'  folder for the results CSV and PNG files (default current folder)
%
%   No toolboxes are needed (base MATLAB R2016b or newer).
%
%   Steps: (1) build the radio graph, (2) build the distance-2 conflict graph,
%   (3) colour it with DSATUR + random restarts, (4) verify no conflicts,
%   (5) run slot-by-slot reception simulation for several schedules.
%
%   Reception rule for every transmission t -> receiver r in range, per slot:
%     r transmitting itself        -> lost (half duplex)
%     another transmitter in range of r -> lost (collision at r)
%         hidden terminal: the interferer is NOT in range of t
%         direct:          the interferer is in range of t
%     otherwise                    -> delivered

    p = inputParser;
    addParameter(p, 'Csv', '');
    addParameter(p, 'Range', 500);
    addParameter(p, 'SlotMs', 1);
    addParameter(p, 'Random', 200);
    addParameter(p, 'Plots', true);
    addParameter(p, 'OutDir', pwd);
    parse(p, varargin{:});
    o = p.Results;
    rng(42);

    % ---- 1. topology -------------------------------------------------------------
    brainSlots = [];
    if isempty(o.Csv)
        [gx, gy] = meshgrid(0:300:900, 0:300:900);          % Node_01 (0,0) ... Node_16 (900,900)
        X = reshape(gx', [], 1); Y = reshape(gy', [], 1);
        names = arrayfun(@(k) sprintf('Node_%02d', k), (1:16)', 'UniformOutput', false);
    else
        [names, X, Y, brainSlots] = read_csv(o.Csv);
    end
    n = numel(X);
    D = sqrt((X - X').^2 + (Y - Y').^2);
    A = (D <= o.Range) & ~eye(n);                            % radio graph, inclusive range
    fprintf('TDMA schedule simulation (MATLAB)\n');
    fprintf('  radios: %d, range: %g m, links: %d\n', n, o.Range, nnz(A) / 2);

    % ---- 2/3. distance-2 conflict graph and colouring --------------------------------
    A2 = ((double(A) * double(A)) > 0) | A;                  % within 1 or 2 hops
    A2(1:n+1:end) = false;                                   % G squared, no self loops
    [slots, S] = dsatur_best(A2, 300);
    lb = max(sum(A, 2)) + 1;                                 % a node and its neighbours form a clique in G^2
    fprintf('  MATLAB colouring: %d slots (lower bound %d) -> %s\n', S, lb, ...
        ternary(S == lb, 'PROVEN OPTIMAL', 'best found, not proven'));

    % ---- 4. verification straight from the coordinates ---------------------------------
    nViol = count_conflicts(slots, D, o.Range);
    fprintf('  Verification: %d conflicting pairs -> %s\n\n', nViol, ternary(nViol == 0, 'PASS', 'FAIL'));

    % ---- 5. scenarios -------------------------------------------------------------------
    scen = {};  % each: name, slots (0-based), slots per frame
    scen(end+1, :) = {'MATLAB schedule (distance-2 colouring)', slots, S};
    if ~isempty(brainSlots)
        scen(end+1, :) = {'Python Brain schedule (from CSV)', brainSlots, max(brainSlots) + 1};
    end
    ref = slots;
    if ~isempty(brainSlots), ref = brainSlots; end
    i1 = find(strcmp(names, 'Node_01')); i3 = find(strcmp(names, 'Node_03'));
    if ~isempty(i1) && ~isempty(i3)
        bad = ref; bad(i3) = bad(i1);
        scen(end+1, :) = {'Bad: Node_03 in Node_01''s slot', bad, max(ref) + 1};
    end
    scen(end+1, :) = {'Token passing (1 node per slot)', (0:n-1)', n};
    scen(end+1, :) = {'All nodes in one slot', zeros(n, 1), 1};

    rows = zeros(0, 9);  labels = {};
    for k = 1:size(scen, 1)
        r = simulate(scen{k, 2}, A);
        rows(end+1, :) = metrics(r, scen{k, 3}, o.SlotMs);  %#ok<AGROW>
        labels{end+1} = scen{k, 1};                         %#ok<AGROW>
    end
    % random schedules with the Brain/MATLAB frame length
    Sref = S; if ~isempty(brainSlots), Sref = max(brainSlots) + 1; end
    acc = zeros(1, 6);
    for k = 1:o.Random
        acc = acc + simulate(randi([0 Sref-1], n, 1), A);
    end
    rows(end+1, :) = metrics(acc / o.Random, Sref, o.SlotMs);
    labels{end+1} = sprintf('Random schedule (mean of %d)', o.Random);

    % ---- report -------------------------------------------------------------------------
    fprintf('%-40s %6s %10s %9s %8s %8s %9s %12s\n', 'Scenario', 'Slots', 'Delivered', 'Collided', 'Hidden', 'Direct', 'Delivery', 'Deliv./sec');
    fprintf('%s\n', repmat('-', 1, 112));
    for k = 1:size(rows, 1)
        fprintf('%-40s %6d %10.2f %9.2f %8.2f %8.2f %8.2f%% %12.0f\n', labels{k}, rows(k, 1), rows(k, 3), ...
            rows(k, 4), rows(k, 5), rows(k, 6), rows(k, 8) * 100, rows(k, 9));
    end
    fprintf('\n(per-frame figures; "Delivered" counts transmitter-to-neighbour receptions)\n');
    gain = rows(1, 9) / rows(strcmp(labels, 'Token passing (1 node per slot)'), 9);
    fprintf('Capacity gain of the schedule over token passing: %.2fx\n', gain);

    csvPath = fullfile(o.OutDir, 'matlab_results.csv');
    fid = fopen(csvPath, 'w');
    fprintf(fid, 'scenario,slots_per_frame,attempted_per_frame,delivered_per_frame,collisions_per_frame,hidden_terminal_per_frame,direct_per_frame,half_duplex_per_frame,delivery_ratio,delivered_per_second\n');
    for k = 1:size(rows, 1)
        fprintf(fid, '"%s",%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.6f,%.2f\n', labels{k}, rows(k, 1), rows(k, 2), rows(k, 3), ...
            rows(k, 4), rows(k, 5), rows(k, 6), rows(k, 7), rows(k, 8), rows(k, 9));
    end
    fclose(fid);
    fprintf('Results written to %s\n', csvPath);

    % ---- plots --------------------------------------------------------------------------
    if o.Plots
        draw_schedule(X, Y, A, slots, S, names);
        save_fig(gcf, fullfile(o.OutDir, 'matlab_schedule.png'));
        figure('Name', 'Delivery ratio', 'Color', 'w');
        bar(rows(:, 8) * 100); grid on;
        set(gca, 'XTick', 1:numel(labels), 'XTickLabel', shorten(labels), 'XTickLabelRotation', 25);
        ylabel('Receptions delivered (%)'); title('Delivery ratio by schedule'); ylim([0 105]);
        save_fig(gcf, fullfile(o.OutDir, 'matlab_delivery.png'));
        figure('Name', 'Throughput', 'Color', 'w');
        bar(rows(:, 9)); grid on;
        set(gca, 'XTick', 1:numel(labels), 'XTickLabel', shorten(labels), 'XTickLabelRotation', 25);
        ylabel('Delivered receptions per second'); title('Throughput by schedule');
        save_fig(gcf, fullfile(o.OutDir, 'matlab_throughput.png'));
        fprintf('Figures saved in %s\n', o.OutDir);
    end
end

% =====================================================================================
function [slots, S] = dsatur_best(A2, restarts)
    n = size(A2, 1);
    best = []; S = inf;
    for r = 1:restarts
        c = dsatur(A2, r > 1);
        k = max(c) + 1;
        if k < S, S = k; best = c; end
    end
    slots = best;
end

function c = dsatur(A2, randomTies)
    n = size(A2, 1);
    c = -ones(n, 1);
    deg = sum(A2, 2);
    for step = 1:n
        sat = zeros(n, 1);
        for v = 1:n
            if c(v) < 0, sat(v) = numel(unique(c(A2(:, v) & c >= 0))); end
        end
        cand = find(c < 0);
        key = sat(cand) * 1e4 + deg(cand);
        if randomTies, key = key + rand(numel(cand), 1) * 0.9; else, key = key - cand * 1e-6; end
        [~, ix] = max(key);
        v = cand(ix);
        used = unique(c(A2(:, v) & c >= 0));
        col = 0;
        while any(used == col), col = col + 1; end
        c(v) = col;
    end
end

function nViol = count_conflicts(slots, D, R)
% Independent check from raw distances: same slot and 1 or 2 hops apart is a conflict.
    n = numel(slots); nViol = 0;
    A = (D <= R) & ~eye(n);
    for i = 1:n
        for j = i+1:n
            if slots(i) ~= slots(j), continue; end
            if A(i, j) || any(A(i, :) & A(j, :)), nViol = nViol + 1; end
        end
    end
end

function r = simulate(slots, A)
% One frame. Returns [attempted success collided hidden direct halfduplex].
    n = numel(slots); r = zeros(1, 6);
    for s = unique(slots(:))'
        tx = find(slots(:) == s)';
        for t = tx
            for rx = find(A(t, :))
                r(1) = r(1) + 1;
                if slots(rx) == s, r(6) = r(6) + 1; continue; end
                others = tx(tx ~= t & A(tx, rx)');
                if isempty(others)
                    r(2) = r(2) + 1;
                else
                    r(3) = r(3) + 1;
                    if any(~A(t, others)), r(4) = r(4) + 1; else, r(5) = r(5) + 1; end
                end
            end
        end
    end
end

function m = metrics(r, S, slotMs)
% [S attempted delivered collided hidden direct halfduplex ratio perSecond]
    ratio = r(2) / r(1);
    perSec = r(2) / (S * slotMs / 1000);
    m = [S, r(1), r(2), r(3), r(4), r(5), r(6), ratio, perSec];
end

function [names, X, Y, slots] = read_csv(path)
    fid = fopen(path, 'r'); assert(fid > 0, 'Cannot open %s', path);
    names = {}; X = []; Y = []; slots = [];
    while true
        line = fgetl(fid);
        if ~ischar(line), break; end
        line = strtrim(line);
        if isempty(line) || line(1) == '#' || strncmpi(line, 'name', 4), continue; end
        f = strsplit(line, ',');
        names{end+1, 1} = f{1};  X(end+1, 1) = str2double(f{2});  %#ok<AGROW>
        Y(end+1, 1) = str2double(f{3});  slots(end+1, 1) = str2double(f{4});
    end
    fclose(fid);
end

function draw_schedule(X, Y, A, slots, S, names)
    figure('Name', 'Schedule', 'Color', 'w'); hold on; axis equal; grid on;
    n = numel(X);
    for i = 1:n
        for j = i+1:n
            if A(i, j), plot([X(i) X(j)], [Y(i) Y(j)], '-', 'Color', [0.7 0.7 0.7]); end
        end
    end
    cm = hsv(S);
    for i = 1:n
        plot(X(i), Y(i), 'o', 'MarkerSize', 26, 'MarkerFaceColor', cm(slots(i) + 1, :), 'MarkerEdgeColor', 'k');
        text(X(i), Y(i), sprintf('%s\nS%d', names{i}(end-1:end), slots(i)), 'HorizontalAlignment', 'center', 'FontSize', 8);
    end
    title(sprintf('TDMA schedule: %d slots (same colour = same slot)', S));
    xlabel('x (m)'); ylabel('y (m)'); hold off;
end

function save_fig(h, path)
    try
        exportgraphics(h, path, 'Resolution', 150);
    catch
        try
            saveas(h, path);
        catch
            warning('Could not save %s', path);
        end
    end
end

function out = shorten(labels)
    out = cellfun(@(s) regexprep(s, ' \(.*$', ''), labels, 'UniformOutput', false);
end

function v = ternary(c, a, b)
    if c, v = a; else, v = b; end
end
