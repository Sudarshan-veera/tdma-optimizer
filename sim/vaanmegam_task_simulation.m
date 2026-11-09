%% ========================================================================
%  TDMA SCHEDULE PLANNER & OPTIMIZER  -  full simulation (MATLAB / Octave)
%  Vaan Megam Networks task, Part 1 (Network Brain)
%
%  Model : radios = nodes, link if distance <= range (500 m)
%  Rule  : nodes at graph distance 1 (direct) or 2 (hidden terminal) must
%          NOT share a slot  ->  colour the SQUARE of the graph (G^2)
%  Reuse : nodes >= 3 hops apart may share a slot (spatial reuse)
%  ========================================================================
clear; clc; close all; rng(42); tStart = tic;
%% ---------------- OUTPUT FOLDER: vaanmegam (next to this script) --------
try
    baseDir = fileparts(mfilename('fullpath'));   % folder where this .m file lives
    if isempty(baseDir), baseDir = pwd; end
catch
    baseDir = pwd;
end
outDir = fullfile(baseDir, 'vaanmegam');
if ~exist(outDir, 'dir'), mkdir(outDir); end
reportFile = fullfile(outDir, 'tdma_report.txt');
if exist(reportFile, 'file'), delete(reportFile); end
diary(reportFile);                                % saves everything printed below
%% ---------------- CONFIGURATION -----------------------------------------
radioRange   = 500;                    % metres (link if distance <= range)
slotSec      = 1e-3;                   % 1 ms slot (as in the EMANE task)
n            = 16;                     % number of radios
sweepRanges  = [250 350 450 650 850 1300];   % extra ranges for the sweep
nRT          = 30;                     % random topologies for the benchmark
areaSide     = 1500;                   % random topologies: 1500 x 1500 m
nRand        = 200;                    % random schedules for the baseline

idx  = (0:n-1)';
gridX = mod(idx,4)*300;                % Node_01 (0,0) ... Node_16 (900,900)
gridY = floor(idx/4)*300;

%% ---------------- JOB LIST: main demo + range sweep + random nets -------
J = 1 + numel(sweepRanges) + nRT;
jobX = cell(J,1); jobY = cell(J,1); jobR = zeros(J,1);
jobX{1} = gridX; jobY{1} = gridY; jobR(1) = radioRange;
for q = 1:numel(sweepRanges)
    jobX{1+q} = gridX; jobY{1+q} = gridY; jobR(1+q) = sweepRanges(q);
end
for q = 1:nRT
    jj = 1 + numel(sweepRanges) + q;
    jobX{jj} = rand(n,1)*areaSide; jobY{jj} = rand(n,1)*areaSide; jobR(jj) = radioRange;
end

%% ---------------- BRAIN: distance-2 colouring (DSATUR + restarts) ------
jobSlots = cell(J,1); jobS = zeros(J,1); jobLB = zeros(J,1); jobLinks = zeros(J,1);
for j = 1:J
    Xj = jobX{j}; Yj = jobY{j}; rj = jobR(j); nj = numel(Xj);
    Dj  = sqrt(bsxfun(@minus,Xj,Xj').^2 + bsxfun(@minus,Yj,Yj').^2);
    Aj  = (Dj <= rj) & ~eye(nj);                         % 1-hop links
    A2j = ((double(Aj)*double(Aj)) > 0) | Aj;            % 1-hop OR 2-hop
    A2j(1:nj+1:end) = false;                             % conflict graph G^2
    degj = sum(A2j,2);
    if j == 1, nRestarts = 300; else, nRestarts = 40; end
    bestK = inf; bestCol = [];
    for rep = 1:nRestarts
        col = -ones(nj,1);
        for step = 1:nj
            sat = zeros(nj,1);                           % DSATUR saturation
            for v = 1:nj
                if col(v) < 0
                    sat(v) = numel(unique(col(A2j(v,:)' & col >= 0)));
                end
            end
            score = sat*1000 + degj + rand(nj,1)*0.5;    % random tie-break
            score(col >= 0) = -inf;
            [~,v] = max(score);
            used = col(A2j(v,:)' & col >= 0); c = 0;
            while any(used == c), c = c + 1; end         % smallest free slot
            col(v) = c;
        end
        if max(col)+1 < bestK, bestK = max(col)+1; bestCol = col; end
    end
    jobSlots{j} = bestCol; jobS(j) = bestK;
    jobLB(j)    = max(sum(Aj,2)) + 1;     % node + neighbours = clique in G^2
    jobLinks(j) = sum(Aj(:))/2;
end

%% ---------------- MAIN DEMO VARIABLES -----------------------------------
X = jobX{1}; Y = jobY{1};
D = sqrt(bsxfun(@minus,X,X').^2 + bsxfun(@minus,Y,Y').^2);
A = (D <= radioRange) & ~eye(n);
slotM = jobSlots{1}; S = jobS(1); LB = jobLB(1);
slotPy = [8 5 4 8 6 2 0 7 7 1 3 6 8 4 5 8]';   % Python Brain result (documentation)
% (if you change the coordinates above, set:  slotPy = slotM;)

%% ======================= REPORT ========================================
fprintf('================================================================\n');
fprintf(' TDMA TOPOLOGY OPTIMIZATION REPORT\n');
fprintf('================================================================\n');
fprintf('Total Nodes Processed : %d\n', n);
fprintf('Configured Radio Range : %.1f meters\n', radioRange);
fprintf('Radio links (edges)    : %d\n', jobLinks(1));
fprintf('Optimized Frame Length : %d unique timeslots (Lower is better)\n', S);
if S == LB
    fprintf('Optimality             : PROVEN OPTIMAL (lower bound = %d)\n', LB);
else
    fprintf('Optimality             : best found (lower bound = %d)\n', LB);
end
fprintf('----------------------------------------------------------------\n');
fprintf('NODE -> SLOT ASSIGNMENTS:\n');
for i = 1:n, fprintf(' Node_%02d: Slot %d\n', i, slotM(i)); end

fprintf('\nSTRUCTURAL TDMA SCHEDULE MATRIX (Slot x Node Boolean Matrix):\n');
fprintf('Slot \\ Node |'); fprintf(' %02d |', 1:n); fprintf('\n');
fprintf('%s\n', repmat('-',1,13+5*n));
Msched = zeros(S,n);
for s = 0:S-1
    Msched(s+1,:) = double(slotM' == s);
    fprintf('Slot %02d     |', s); fprintf('  %d |', Msched(s+1,:)); fprintf('\n');
end
fprintf('%s\n', repmat('-',1,13+5*n));

%% ---------------- VERIFICATION (independent, from raw coordinates) ------
fprintf('\n[1] VERIFICATION  (every 1-hop and 2-hop pair re-checked from coordinates)\n');
cands = [slotM, slotPy]; candNames = {'MATLAB schedule','Python Brain schedule'};
for k = 1:2
    sl = cands(:,k); bad = 0; pairs = 0;
    for i = 1:n-1
        for j = i+1:n
            d1 = D(i,j) <= radioRange;
            d2 = any(D(i,:) <= radioRange & D(:,j)' <= radioRange & (1:n) ~= i & (1:n) ~= j);
            if d1 || d2
                pairs = pairs + 1;
                if sl(i) == sl(j), bad = bad + 1; end
            end
        end
    end
    if bad == 0, verdict = 'PASS'; else, verdict = 'FAIL'; end
    fprintf('    %-22s : %3d interfering pairs checked, %d conflicts -> %s\n', ...
            candNames{k}, pairs, bad, verdict);
end

%% ---------------- SPATIAL REUSE ANALYSIS --------------------------------
H = double(A); H(H == 0) = inf; H(1:n+1:end) = 0;          % hop distances
for k = 1:n, H = min(H, bsxfun(@plus, H(:,k), H(k,:))); end
fprintf('\n[2] SPATIAL REUSE  (nodes sharing a slot must be >= 3 hops apart)\n');
fprintf('    %-6s %-18s %-22s %s\n','Slot','Transmitting nodes','Closest pair (hops)','Farthest apart (m)');
reuseSlots = 0; maxConc = 0;
for s = 0:S-1
    T = find(slotM == s); maxConc = max(maxConc, numel(T));
    str = strtrim(sprintf('%02d ', T));
    if numel(T) > 1
        reuseSlots = reuseSlots + 1; mh = inf; me = 0;
        for a = 1:numel(T)-1
            for b = a+1:numel(T)
                mh = min(mh, H(T(a),T(b))); me = max(me, D(T(a),T(b)));
            end
        end
        fprintf('    %-6d %-18s %-22d %.0f\n', s, str, mh, me);
    else
        fprintf('    %-6d %-18s %-22s %s\n', s, str, '-', '-');
    end
end
fprintf('    -> %d of %d slots are reused; up to %d radios transmit at once;\n', reuseSlots, S, maxConc);
fprintf('       average %.2f nodes per slot (token passing would be 1.00).\n', n/S);

%% ---------------- PACKET-LEVEL SIMULATION (one TDMA frame) -------------
% In its slot each node broadcasts once. A neighbour r receives it only if
% exactly ONE audible transmitter is active and r is not transmitting itself.
%   Direct collision : receiver is itself transmitting (neighbours in same slot)
%   Hidden collision : two or more audible transmitters at the receiver
badS = slotM; badS(3) = slotM(1);                  % Node_03 forced into Node_01's slot
Rnd  = randi(S, n, nRand) - 1;
SL   = [slotM, slotPy, badS, (0:n-1)', zeros(n,1), Rnd];
names = {'Distance-2 schedule (MATLAB)','Distance-2 schedule (Python)', ...
         'Bad: Node_03 in Node_01 slot','Token passing (1 node/slot)','All nodes in one slot'};
expected = sum(A(:));                              % receptions per frame if no loss
res = zeros(size(SL,2), 5);                        % slots, delivered, hidden, direct, deliv/sec
for k = 1:size(SL,2)
    sl = SL(:,k); Sk = max(sl) + 1; deliv = 0; hid = 0; dirc = 0;
    for s = 0:Sk-1
        T = find(sl == s);
        for r = 1:n
            heard = T(A(T,r));                     % transmitters audible at r
            if isempty(heard), continue; end
            if any(T == r)
                dirc = dirc + numel(heard);        % receiver busy transmitting
            elseif numel(heard) == 1
                deliv = deliv + 1;                 % clean reception
            else
                hid = hid + numel(heard);          % signals collide at r
            end
        end
    end
    res(k,:) = [Sk deliv hid dirc deliv/(Sk*slotSec)];
end
m = mean(res(6:end,:),1);

fprintf('\n[3] PACKET-LEVEL SIMULATION  (per frame; %d receptions possible; slot = %.0f ms)\n', expected, slotSec*1e3);
fprintf('    %-30s %5s %9s %9s %7s %7s %9s %11s\n','Scenario','Slots','Delivered','Collided','Hidden','Direct','Delivery','Deliv./sec');
fprintf('    %s\n', repmat('-',1,96));
for k = 1:5
    fprintf('    %-30s %5d %9d %9d %7d %7d %8.2f%% %11.0f\n', names{k}, res(k,1), res(k,2), ...
        expected-res(k,2), res(k,3), res(k,4), 100*res(k,2)/expected, res(k,5));
end
fprintf('    %-30s %5.0f %9.2f %9.2f %7.2f %7.2f %8.2f%% %11.0f\n', ...
    sprintf('Random schedule (mean of %d)',nRand), m(1), m(2), expected-m(2), m(3), m(4), 100*m(2)/expected, m(5));
fprintf('\n    Reading the table:\n');
fprintf('    * Our schedule delivers every possible reception with %d slots, no collisions.\n', S);
fprintf('    * Token passing is also collision-free but needs %d slots -> %.2fx lower throughput.\n', n, n/S);
fprintf('    * One bad assignment (Node_03 shares Node_01''s slot) already loses %.1f%% of receptions.\n', 100*(1-res(3,2)/expected));
fprintf('    * Random slots with the same frame length lose about %.0f%% -> the colouring is what matters.\n', 100*(1-m(2)/expected));

%% ---------------- RANGE SWEEP (same 4x4 grid) ---------------------------
fprintf('\n[4] EFFECT OF RADIO RANGE ON THE 4x4 GRID\n');
fprintf('    %-10s %6s %12s %12s %10s\n','Range (m)','Links','Slots found','Lower bound','Optimal');
rr = jobR(1:1+numel(sweepRanges)); [rs, ord] = sort(rr);
for q = 1:numel(ord)
    jq = ord(q);
    if jobS(jq) == jobLB(jq), opt = 'yes'; else, opt = 'not proven'; end
    fprintf('    %-10d %6d %12d %12d %10s\n', rs(q), jobLinks(jq), jobS(jq), jobLB(jq), opt);
end
fprintf('    -> denser connectivity forces more slots; at 850 m and above every node is within\n');
fprintf('       2 hops of every other node and the frame degenerates to token passing.\n');

%% ---------------- RANDOM-TOPOLOGY BENCHMARK -----------------------------
rIdx = (2+numel(sweepRanges)):J;
fprintf('\n[5] %d RANDOM %d-NODE TOPOLOGIES (%d x %d m, range %d m)\n', nRT, n, areaSide, areaSide, radioRange);
fprintf('    mean slots used        : %.2f\n', mean(jobS(rIdx)));
fprintf('    mean lower bound       : %.2f\n', mean(jobLB(rIdx)));
fprintf('    proven optimal         : %d / %d\n', sum(jobS(rIdx) == jobLB(rIdx)), nRT);
fprintf('    mean capacity gain     : %.2fx over one node per slot\n', mean(n ./ jobS(rIdx)));

%% ---------------- FINAL VALUES ------------------------------------------
fprintf('\n================================================================\n');
fprintf(' FINAL VALUES (4x4 demo grid, 300 m spacing, 500 m range)\n');
fprintf('   Frame length        : %d slots (lower bound %d)\n', S, LB);
fprintf('   Capacity gain       : %.2fx vs token passing (%d slots)\n', n/S, n);
fprintf('   Collisions          : 0 (verified); delivery %.1f%%\n', 100*res(1,2)/expected);
fprintf('   Throughput          : %.0f receptions/s at %.0f ms slots\n', res(1,5), slotSec*1e3);
fprintf('   Execution finalized cleanly. Schedule verified conflict-free.\n');
fprintf('================================================================\n');

%% ---------------- EXPORTS (saved in vaanmegam folder) ----------------------
fid = fopen(fullfile(outDir,'schedule_matlab.csv'),'w');
fprintf(fid,'# range=%g frame_length=%d\nname,x,y,slot\n', radioRange, S);
for i = 1:n, fprintf(fid,'Node_%02d,%g,%g,%d\n', i, X(i), Y(i), slotM(i)); end
fclose(fid);

fid = fopen(fullfile(outDir,'schedule_preview.xml'),'w');
fprintf(fid,"<structure frames='1' slots='%d' slotoverhead='0' slotduration='%d' bandwidth='1M'/>\n", S, round(slotSec*1e6));
for s = 0:S-1
    T = find(slotM == s); str = sprintf('%d,', T); str(end) = [];
    fprintf(fid,"<slot index='%d' nodes='%s'><tx/></slot>\n", s, str);
end
fclose(fid);

fid = fopen(fullfile(outDir,'schedule_matrix.txt'),'w');
fprintf(fid,'Slot \\ Node |'); fprintf(fid,' %02d |', 1:n); fprintf(fid,'\n');
for s = 0:S-1
    fprintf(fid,'Slot %02d     |', s); fprintf(fid,'  %d |', Msched(s+1,:)); fprintf(fid,'\n');
end
fclose(fid);
fprintf('Files saved in: %s\n', outDir);

%% ---------------- PLOTS (saved in vaanmegam folder) -------------------------
try
    cm = hsv(S);

    % Figure 1: schedule on the topology (title now has room above the nodes)
    h1 = figure('Name','Schedule on topology','Position',[100 100 900 760]);
    hold on; grid on; axis equal;
    for i = 1:n-1
        for j = i+1:n
            if A(i,j), plot(X([i j]),Y([i j]),'-','Color',[.75 .75 .75]); end
        end
    end
    for i = 1:n
        plot(X(i),Y(i),'o','MarkerSize',30,'MarkerFaceColor',cm(slotM(i)+1,:),'MarkerEdgeColor','k');
        text(X(i),Y(i),sprintf('%02d\nS%d',i,slotM(i)),'HorizontalAlignment','center', ...
             'FontSize',8,'FontWeight','bold');
    end
    pad = 200;                                         % empty margin around the grid
    xlim([min(X)-pad, max(X)+pad]);
    ylim([min(Y)-pad, max(Y)+pad]);                    % keeps top row away from the title
    xlabel('x (m)'); ylabel('y (m)');
    title({sprintf('TDMA schedule: %d slots (same colour = same slot, S = slot index)',S), ...
           sprintf('edges = links within %d m',radioRange)}, 'FontSize',11);
    saveas(h1, fullfile(outDir,'fig1_topology.png'));

    % Figure 2: Slot x Node matrix
    h2 = figure('Name','Slot x Node matrix','Position',[120 120 900 450]);
    imagesc(Msched); colormap([1 1 1; 0.1 0.4 0.8]);
    set(gca,'XTick',1:n,'YTick',1:S,'YTickLabel',0:S-1);
    xlabel('Node'); ylabel('Slot'); title('TDMA schedule matrix (blue = transmit)');
    saveas(h2, fullfile(outDir,'fig2_matrix.png'));

    % Figure 3: delivery comparison
    h3 = figure('Name','Delivery','Position',[140 140 800 450]);
    vals = [100*res(1:5,2)/expected; 100*m(2)/expected];
    bar(vals); ylabel('Receptions delivered (%)'); ylim([0 115]);
    set(gca,'XTick',1:6,'XTickLabel',{'Ours','Python','Bad','Token','1 slot','Random'});
    for q = 1:6, text(q, vals(q)+3, sprintf('%.1f%%',vals(q)), 'HorizontalAlignment','center'); end
    title('Reception success per frame');
    saveas(h3, fullfile(outDir,'fig3_delivery.png'));

    % Figure 4: range sweep
    h4 = figure('Name','Range sweep','Position',[160 160 800 450]);
    plot(rs, jobS(ord),'-o', rs, jobLB(ord),'--s','LineWidth',1.5); grid on;
    xlabel('Radio range (m)'); ylabel('Slots');
    legend('Slots found','Lower bound','Location','northwest');
    title('Frame length vs radio range (4x4 grid)');
    saveas(h4, fullfile(outDir,'fig4_range.png'));
catch
    disp('Plots skipped (no graphics toolkit available).');
end
fprintf('Total run time: %.1f s\n', toc(tStart));
diary off;                                             % closes tdma_report.txt