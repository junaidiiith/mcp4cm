import { FileUp, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import type {
  BusyState,
  FormatOption,
  Language,
  RepresentationProfile,
  UploadFormat,
  UploadParseJob,
} from "../../types";

type DirectoryInputAttributes = {
  webkitdirectory?: string;
  directory?: string;
};

export function UploadPanel({
  language,
  format,
  formatOptions,
  files,
  directoryMode,
  selectedFormat,
  representationEnabled,
  representation,
  busy,
  datasetId,
  uploadParseJob,
  uploadedFiles,
  fileDropText,
  onLanguageChange,
  onFormatChange,
  onFilesChange,
  onRepresentationChange,
  onParse,
}: {
  language: Language;
  format: UploadFormat;
  formatOptions: FormatOption[];
  files: File[];
  directoryMode: boolean;
  selectedFormat: FormatOption;
  representationEnabled: boolean;
  representation: RepresentationProfile;
  busy: BusyState;
  datasetId: string;
  uploadParseJob: UploadParseJob | null;
  uploadedFiles: number;
  fileDropText: string;
  onLanguageChange: (language: Language) => void;
  onFormatChange: (format: UploadFormat) => void;
  onFilesChange: (files: File[]) => void;
  onRepresentationChange: (patch: Partial<RepresentationProfile>) => void;
  onParse: () => void;
}) {
  const directoryInputAttributes: DirectoryInputAttributes = directoryMode
    ? { webkitdirectory: "", directory: "" }
    : {};

  return (
    <Card className="panel" id="upload">
      <CardHeader className="panelHeader">
        <h2>
          <Upload size={20} />
          Dataset Upload
        </h2>
      </CardHeader>
      <CardContent>
        <div className="stepGrid">
          <div className="stepCard">
            <h3>Source</h3>
            <div className="uploadGrid">
              <Label>
                Modeling language
                <select value={language} onChange={(event) => onLanguageChange(event.target.value as Language)}>
                  <option value="uml">UML</option>
                  <option value="ecore">Ecore</option>
                  <option value="archimate">ArchiMate</option>
                  <option value="bpmn">BPMN</option>
                </select>
              </Label>
              <Label>
                Parser format
                <select value={format} onChange={(event) => onFormatChange(event.target.value as UploadFormat)}>
                  {formatOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Label>
              <label className="fileDrop">
                <FileUp size={24} />
                <span>{fileDropText}</span>
                <input
                  type="file"
                  multiple
                  accept={selectedFormat.accept}
                  {...directoryInputAttributes}
                  onChange={(event) => {
                    onFilesChange(Array.from(event.target.files || []));
                  }}
                />
              </label>
            </div>
          </div>
          {representationEnabled && (
            <div className="stepCard">
              <h3>Parse Options</h3>
              <div className="representationChecks">
                <label className="inlineCheck">
                  <input
                    type="checkbox"
                    checked={representation.includeAttributes}
                    onChange={(event) => onRepresentationChange({ includeAttributes: event.target.checked })}
                  />
                  Attributes as nodes
                </label>
                <label className="inlineCheck">
                  <input
                    type="checkbox"
                    checked={representation.includeOperations}
                    onChange={(event) => onRepresentationChange({ includeOperations: event.target.checked })}
                  />
                  Operations as nodes
                </label>
                <label className="inlineCheck">
                  <input
                    type="checkbox"
                    checked={representation.includeParameters}
                    onChange={(event) => onRepresentationChange({ includeParameters: event.target.checked })}
                  />
                  Parameters as nodes
                </label>
                <label className="inlineCheck">
                  <input
                    type="checkbox"
                    checked={representation.includeModelRootNode}
                    onChange={(event) => onRepresentationChange({ includeModelRootNode: event.target.checked })}
                  />
                  Create model root node
                </label>
              </div>
            </div>
          )}
        </div>
        <div className="actionBar">
          <Button type="button" variant="default" disabled={!files.length || busy === "parse"} onClick={onParse}>
            {busy === "parse" ? <Loader2 className="spin" size={18} /> : <FileUp size={18} />}
            {datasetId ? "Reparse Dataset" : "Parse Dataset"}
          </Button>
        </div>
        {(busy === "parse" || uploadParseJob) && (
          <UploadParseProgress totalFiles={files.length} uploadedFiles={uploadedFiles} job={uploadParseJob} />
        )}
      </CardContent>
    </Card>
  );
}

function UploadParseProgress({
  totalFiles,
  uploadedFiles,
  job,
}: {
  totalFiles: number;
  uploadedFiles: number;
  job: UploadParseJob | null;
}) {
  const uploadPercent = totalFiles ? Math.round((uploadedFiles / totalFiles) * 100) : 0;
  const parseTotal = job?.parseTotalFiles || job?.totalFiles || totalFiles;
  const parseProcessed = job?.parseProcessedFiles || 0;
  const parsePercent = parseTotal ? Math.round((parseProcessed / parseTotal) * 100) : 0;
  return (
    <div className="uploadProgress">
      <h3>Processing Progress</h3>
      <div className="uploadProgressRow">
        <span>Files uploaded</span>
        <strong>
          {uploadedFiles} / {totalFiles}
        </strong>
      </div>
      <div className="progressTrack">
        <div className="progressFill" style={{ width: `${uploadPercent}%` }} />
      </div>
      <div className="uploadProgressRow">
        <span>Parse</span>
        <strong>
          {parseProcessed} / {parseTotal || "-"}
        </strong>
      </div>
      <div className="progressTrack">
        <div className="progressFill secondary" style={{ width: `${parsePercent}%` }} />
      </div>
      <p>{job?.message || "Preparing upload..."}</p>
    </div>
  );
}
