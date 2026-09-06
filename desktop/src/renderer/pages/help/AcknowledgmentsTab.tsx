import { Card, CardBody, CardHeader } from "../../ui/Layout";

/** Ported verbatim from tit/gui/acknowledgments_tab.py — same titles, same reference text. */
const ACKNOWLEDGMENTS: { title: string; content: string }[] = [
  {
    title: "TI-Toolbox",
    content:
      "Haber I, Jackson A, Thielscher A, Hai A, Tononi G. Temporal Interference Toolbox: A comprehensive pipeline for transcranial electrical stimulation optimization. bioRxiv 2025.10.06.680781; https://doi.org/10.1101/2025.10.06.680781.",
  },
  {
    title: "SimNIBS CHARM Segmentation Pipeline",
    content:
      "Puonti O, Van Leemput K, Saturnino GB, Siebner HR, Madsen KH, Thielscher A. (2020). Accurate and robust whole-head segmentation from magnetic resonance images for individualized head modeling. Neuroimage, 219:117044.",
  },
  {
    title: "Flex-Search Optimization Algorithm",
    content:
      "Weise K, Madsen KH, Worbs T, Knösche TR, Korshøj A, Thielscher A, A Leadfield-Free Optimization Framework for Transcranially Applied Electric Currents, bioRxiv 10.1101/2024.12.18.629095",
  },
  {
    title: "Noninvasive Deep Brain Stimulation via Temporally Interfering Electric Fields",
    content:
      "Grossman N, Bono D, Dedic N, Kodandaramaiah SB, Rudenko A, Suk HJ, Cassara AM, Neufeld E, Kuster N, Tsai LH, Pascual-Leone A, Boyden ES. Noninvasive Deep Brain Stimulation via Temporally Interfering Electric Fields. Cell. 2017 Jun 1;169(6):1029-1041.e16. doi: 10.1016/j.cell.2017.05.024. PMID: 28575667; PMCID: PMC5520675.",
  },
  {
    title: "FreeSurfer",
    content: "Fischl B. FreeSurfer. Neuroimage. 2012 Aug 15;62(2):774-81. https://doi.org/10.1016/j.neuroimage.2012.01.021.",
  },
  {
    title: "FSL",
    content:
      "M.W. Woolrich, S. Jbabdi, B. Patenaude, M. Chappell, S. Makni, T. Behrens, C. Beckmann, M. Jenkinson, S.M. Smith. Bayesian analysis of neuroimaging data in FSL. NeuroImage, 45:S173-86, 2009\n\n" +
      "S.M. Smith, M. Jenkinson, M.W. Woolrich, C.F. Beckmann, T.E.J. Behrens, H. Johansen-Berg, P.R. Bannister, M. De Luca, I. Drobnjak, D.E. Flitney, R. Niazy, J. Saunders, J. Vickers, Y. Zhang, N. De Stefano, J.M. Brady, and P.M. Matthews. Advances in functional and structural MR image analysis and implementation as FSL. NeuroImage, 23(S1):208-19, 2004\n\n" +
      "M. Jenkinson, C.F. Beckmann, T.E. Behrens, M.W. Woolrich, S.M. Smith. FSL. NeuroImage, 62:782-90, 2012",
  },
  {
    title: "dcm2niix",
    content:
      "Li X, Morgan PS, Ashburner J, Smith J, Rorden C (2016) The first step for neuroimaging data analysis: DICOM to NIfTI conversion. J Neurosci Methods. 264:47-56. doi: 10.1016/j.jneumeth.2016.03.001. PMID: 26945974",
  },
  {
    title: "BIDS",
    content:
      "Gorgolewski, K., Auer, T., Calhoun, V. et al. The brain imaging data structure, a format for organizing and describing outputs of neuroimaging experiments. Sci Data 3, 160044 (2016). https://doi.org/10.1038/sdata.2016.44",
  },
  {
    title: "Docker",
    content: "Merkel, D. (2014). Docker: lightweight Linux containers for consistent development and deployment. Linux Journal, 2014(239), Article 2.",
  },
  {
    title: "Gmsh",
    content:
      "C. Geuzaine and J.-F. Remacle. Gmsh: a three-dimensional finite element mesh generator with built-in pre- and post-processing facilities. International Journal for Numerical Methods in Engineering 79(11), pp. 1309-1331, 2009.",
  },
  { title: "Blender", content: "https://github.com/blender" },
];

export function AcknowledgmentsTab() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <p className="text-body" style={{ color: "var(--ink-2)" }}>
        TI-Toolbox relies on several open-source tools and frameworks. We are grateful to the developers of these resources and acknowledge their
        contributions below.
      </p>
      {ACKNOWLEDGMENTS.map((a) => (
        <Card key={a.title}>
          <CardHeader title={a.title} />
          <CardBody>
            <p className="text-body" style={{ whiteSpace: "pre-line" }}>
              {a.content}
            </p>
          </CardBody>
        </Card>
      ))}
      <p className="text-caption" style={{ color: "var(--ink-3)", fontStyle: "italic", textAlign: "center" }}>
        If you're using TI-Toolbox in academic work, please cite the appropriate references above.
      </p>
    </div>
  );
}
