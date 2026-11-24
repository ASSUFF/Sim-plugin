import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;
import java.util.Locale;

/**
 * Silicon strip waveguide on oxide, 2D cross-section, mode analysis.
 * The propagation direction is out of plane, so the eigenvalue gives the
 * effective mode index. Outer boundaries are PEC; the box is wide enough that
 * the evanescent tail is negligible there.
 */
public class SiStripMode {
    public static void main(String[] args) {
        ModelUtil.initStandalone(false);
        try {
            Model model = ModelUtil.create("SiStripMode");
            model.param().set("W_core", "0.5[um]");
            model.param().set("H_core", "0.22[um]");
            model.param().set("W_box", "4[um]");
            model.param().set("H_box", "4[um]");
            model.param().set("n_core", "3.476");
            model.param().set("n_clad", "1.444");
            model.param().set("lam0", "1550[nm]");
            model.param().set("hauto", "6");
            model.param().set("n_guess", "2.4");
            model.param().set("n_modes", "6");

            model.component().create("comp1", true);
            model.component("comp1").geom().create("geom1", 2);
            model.component("comp1").geom("geom1").create("r_box", "Rectangle");
            model.component("comp1").geom("geom1").feature("r_box").set("size", new String[] {"W_box", "H_box"});
            model.component("comp1").geom("geom1").feature("r_box").set("pos", new String[] {"-W_box/2", "-H_box/2"});
            model.component("comp1").geom("geom1").create("r_core", "Rectangle");
            model.component("comp1").geom("geom1").feature("r_core").set("size", new String[] {"W_core", "H_core"});
            model.component("comp1").geom("geom1").feature("r_core").set("pos", new String[] {"-W_core/2", "-H_core/2"});
            model.component("comp1").geom("geom1").run();

            model.component("comp1").selection().create("selCore", "Box");
            model.component("comp1").selection("selCore").set("entitydim", 2);
            model.component("comp1").selection("selCore").set("xmin", "-W_core/2-1[nm]");
            model.component("comp1").selection("selCore").set("xmax", "W_core/2+1[nm]");
            model.component("comp1").selection("selCore").set("ymin", "-H_core/2-1[nm]");
            model.component("comp1").selection("selCore").set("ymax", "H_core/2+1[nm]");
            model.component("comp1").selection("selCore").set("condition", "inside");

            model.component("comp1").material().create("mat_clad", "Common");
            model.component("comp1").material("mat_clad").selection().all();
            model.component("comp1").material("mat_clad").propertyGroup()
                    .create("RefractiveIndex", "RefractiveIndex", "Refractive_index");
            model.component("comp1").material("mat_clad").propertyGroup("RefractiveIndex")
                    .set("n", new String[] {"n_clad"});

            model.component("comp1").material().create("mat_core", "Common");
            model.component("comp1").material("mat_core").selection().named("selCore");
            model.component("comp1").material("mat_core").propertyGroup()
                    .create("RefractiveIndex", "RefractiveIndex", "Refractive_index");
            model.component("comp1").material("mat_core").propertyGroup("RefractiveIndex")
                    .set("n", new String[] {"n_core"});

            model.component("comp1").physics().create("ewfd", "ElectromagneticWavesFrequencyDomain", "geom1");
            model.component("comp1").physics("ewfd").feature("wee1").set("DisplacementFieldModel", "RefractiveIndex");

            model.component("comp1").mesh().create("mesh1", "geom1");
            int hauto = Integer.parseInt(model.param().get("hauto").trim());
            model.component("comp1").mesh("mesh1").feature("size").set("hauto", hauto);
            model.component("comp1").mesh("mesh1").run();

            model.study().create("std1");
            model.study("std1").create("mode1", "ModeAnalysis");
            double nmodes = Double.parseDouble(model.param().get("n_modes").trim());
            model.study("std1").feature("mode1").set("neigs", (int) nmodes);
            try {
                model.study("std1").feature("mode1").set("modeFreq", "c_const/lam0");
            } catch (Exception exc) {
                System.out.println("PROPFAIL=modeFreq");
                try {
                    model.study("std1").feature("mode1").set("freq", "c_const/lam0");
                } catch (Exception second) {
                    System.out.println("PROPFAIL=freq");
                }
            }
            try {
                model.study("std1").feature("mode1").set("shift", "n_guess");
                model.study("std1").feature("mode1").set("shiftactive", "on");
            } catch (Exception exc) {
                System.out.println("PROPFAIL=shift");
            }
            model.study("std1").run();

            model.result().numerical().create("gev1", "EvalGlobal");
            model.result().numerical("gev1").set("expr", new String[] {"lambda"});
            double[][] lamRe = model.result().numerical("gev1").getReal();
            double[][] lamIm = model.result().numerical("gev1").getImag();
            int count = lamRe.length > 0 ? lamRe[0].length : 0;
            double lam0 = 1550e-9;
            double k0 = 2.0 * Math.PI / lam0;
            double[] neff = new double[count];
            double[] beta = new double[count];
            for (int i = 0; i < count; i++) {
                beta[i] = -lamIm[0][i];
                neff[i] = beta[i] / k0;
            }
            // Sort by descending real effective index.
            for (int i = 0; i < count; i++) {
                for (int j = i + 1; j < count; j++) {
                    if (neff[j] > neff[i]) {
                        double t = neff[i];
                        neff[i] = neff[j];
                        neff[j] = t;
                        double b = beta[i];
                        beta[i] = beta[j];
                        beta[j] = b;
                    }
                }
            }
            System.out.println("MESH_ELEMENTS=" + model.component("comp1").mesh("mesh1").stat().getNumElem());
            System.out.println("MODE_COUNT=" + count);
            for (int i = 0; i < count; i++) {
                System.out.printf(Locale.US, "MODE%d_neff=%.6f%n", i, neff[i]);
            }
            System.out.println("===RESULT===");
            if (count > 0) System.out.printf(Locale.US, "neff_mode0=%.6f%n", neff[0]);
            if (count > 1) System.out.printf(Locale.US, "neff_mode1=%.6f%n", neff[1]);
            if (count > 2) System.out.printf(Locale.US, "neff_mode2=%.6f%n", neff[2]);
            if (count > 0) System.out.printf(Locale.US, "beta_mode0_per_m=%.6f%n", beta[0]);
            System.out.printf(Locale.US, "n_core_used=%.6f%n", Double.parseDouble(model.param().get("n_core").trim()));
            model.save("SiStripMode.mph");
        } catch (Exception e) {
            System.err.println("FATAL: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        } finally {
            ModelUtil.disconnect();
        }
    }
}
