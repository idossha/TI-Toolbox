/** The one subject grammar (plan §3). Pages import from here, never from the files below. */
export { SubjectsField } from "./SubjectsField";
export { presenceColumns, notConvertedColumn, type PresenceLike } from "./columns";
export {
  MODE_NOTE,
  blockedSubjects,
  filterSubjects,
  selectAll,
  subjectsBlockedReason,
  subjectsSummary,
  toggleSelection,
  type BlockedSubject,
  type SubjectsSummary,
} from "./model";
export type { SubjectColumn, SubjectEligibility, SubjectLike, SubjectsFieldProps, SubjectsMode } from "./types";
