import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;
import java.util.Locale;

/**
 * A light beam enters the left edge of a slab and is absorbed by Beer's law.
 * The absorbed power is coupled into steady heat conduction.
 * Both vertical edges are held at T_amb, so the interior temperature rise
 * can be compared with the one-dimensional analytical solution.
 */
public class OptoHeat {
    public static void main(String[] args) {
        ModelUtil.initStandalone(false);
        try {
            Model model = ModelUtil.create("OptoHeat");
            model.param().set("L", "0.02[m]");
            model.param().set("kappa", "50[1/m]");
            model.param().set("I_beam", "1000[W/m^2]");
            model.param().set("k_solid", "0.2[W/(m*K)]");
            model.param().set("rho", "1000[kg/m^3]");
            model.param().set("Cp", "1000[J/(kg*K)]");
            model.param().set("T_amb", "300[K]");

            model.component().create("comp1", true);
            model.component("comp1").geom().create("geom1", 2);
            model.component("comp1").geom("geom1").create("r1", "Rectangle");
            model.component("comp1").geom("geom1").feature("r1").set("size", new String[] {"L", "L"});
            model.component("comp1").geom("geom1").run();

            model.component("comp1").selection().create("selLeft", "Box");
            model.component("comp1").selection("selLeft").set("entitydim", 1);
            model.component("comp1").selection("selLeft").set("xmin", "-1e-6");
            model.component("comp1").selection("selLeft").set("xmax", "1e-6");
            model.component("comp1").selection("selLeft").set("ymin", "-1e-6");
            model.component("comp1").selection("selLeft").set("ymax", "L+1e-6");
            model.component("comp1").selection("selLeft").set("condition", "inside");

            model.component("comp1").selection().create("selRight", "Box");
            model.component("comp1").selection("selRight").set("entitydim", 1);
            model.component("comp1").selection("selRight").set("xmin", "L-1e-6");
            model.component("comp1").selection("selRight").set("xmax", "L+1e-6");
            model.component("comp1").selection("selRight").set("ymin", "-1e-6");
            model.component("comp1").selection("selRight").set("ymax", "L+1e-6");
            model.component("comp1").selection("selRight").set("condition", "inside");

            model.component("comp1").selection().create("selEnds", "Union");
            model.component("comp1").selection("selEnds").set("entitydim", 1);
            model.component("comp1").selection("selEnds").set("input", new String[] {"selLeft", "selRight"});

            model.component("comp1").physics().create("rbam", "RadiativeBeamInAbsorbingMedia", "geom1");
            model.component("comp1").physics("rbam").feature("am1").set("kappaR_mat", "userdef");
            model.component("comp1").physics("rbam").feature("am1").set("kappaR", "kappa");
            model.component("comp1").physics("rbam").create("ii1", "IncidentIntensity", 1);
            model.component("comp1").physics("rbam").feature("ii1").selection().named("selLeft");
            model.component("comp1").physics("rbam").feature("ii1").set("beamProfile", "userdef");
            model.component("comp1").physics("rbam").feature("ii1").set("I0", "I_beam");
            model.component("comp1").physics("rbam").feature("ii1").set("e", new String[] {"1", "0", "0"});

            model.component("comp1").physics().create("ht", "HeatTransfer", "geom1");
            model.component("comp1").physics("ht").feature("solid1").set("k_mat", "userdef");
            model.component("comp1").physics("ht").feature("solid1").set("k", "k_solid");
            model.component("comp1").physics("ht").feature("solid1").set("rho_mat", "userdef");
            model.component("comp1").physics("ht").feature("solid1").set("rho", "rho");
            model.component("comp1").physics("ht").feature("solid1").set("Cp_mat", "userdef");
            model.component("comp1").physics("ht").feature("solid1").set("Cp", "Cp");
            model.component("comp1").physics("ht").create("tempEnds", "TemperatureBoundary", 1);
            model.component("comp1").physics("ht").feature("tempEnds").selection().named("selEnds");
            model.component("comp1").physics("ht").feature("tempEnds").set("T0", "T_amb");

            model.component("comp1").multiphysics().create("htrbam1", "HeatTransferWithRadiativeBeamInAbsorbingMedia");
            model.component("comp1").multiphysics("htrbam1").selection().all();

            model.component("comp1").mesh().create("mesh1", "geom1");
            model.component("comp1").mesh("mesh1").feature("size").set("hauto", 3);
            model.component("comp1").mesh("mesh1").feature("size").set("custom", "on");
            model.component("comp1").mesh("mesh1").feature("size").set("hmax", "L/40");
            model.component("comp1").mesh("mesh1").run();

            model.study().create("std1");
            model.study("std1").create("stat", "Stationary");
            model.study("std1").run();

            double tMax = evaluate(model, "tmax", "T");
            double tMin = evaluate(model, "tmin", "T");
            double iMax = evaluate(model, "imax", "rbam.I");
            double iMin = evaluate(model, "imin", "rbam.I");
            double expected = expectedMax(model);
            System.out.println("===RESULT===");
            System.out.printf(Locale.US, "T_max_K=%.6f%n", tMax);
            System.out.printf(Locale.US, "T_min_K=%.6f%n", tMin);
            System.out.printf(Locale.US, "T_max_expected_K=%.6f%n", expected);
            System.out.printf(Locale.US, "T_max_error_K=%.6f%n", Math.abs(tMax - expected));
            System.out.printf(Locale.US, "I_max=%.6f%n", iMax);
            System.out.printf(Locale.US, "I_min=%.6f%n", iMin);
            model.save("OptoHeat.mph");
        } catch (Exception e) {
            System.err.println("FATAL: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        } finally {
            ModelUtil.disconnect();
        }
    }

    private static double evaluate(Model model, String tag, String expression) {
        String type = tag.startsWith("t") ? "MaxSurface" : "MinSurface";
        if ("tmax".equals(tag) || "imax".equals(tag)) {
            type = "MaxSurface";
        } else {
            type = "MinSurface";
        }
        model.result().numerical().create(tag, type);
        model.result().numerical(tag).selection().all();
        model.result().numerical(tag).set("expr", new String[] {expression});
        double[][] data = model.result().numerical(tag).getReal();
        if (data.length == 0 || data[0].length == 0) {
            throw new IllegalStateException("empty " + expression);
        }
        return data[0][0];
    }

    private static double expectedMax(Model model) {
        double length = model.param().evaluate("L", "m");
        double kappa = model.param().evaluate("kappa", "1/m");
        double intensity = model.param().evaluate("I_beam", "W/m^2");
        double conductivity = model.param().evaluate("k_solid", "W/(m*K)");
        double ambient = model.param().evaluate("T_amb", "K");
        double scale = kappa * intensity / conductivity;
        double decay = kappa * kappa;
        double c2 = ambient + scale / decay;
        double c1 = (scale / decay) * (Math.exp(-kappa * length) - 1.0) / length;
        double best = Double.NEGATIVE_INFINITY;
        for (int i = 0; i <= 400; i++) {
            double x = length * i / 400.0;
            double temperature = -(scale / decay) * Math.exp(-kappa * x) + c1 * x + c2;
            if (temperature > best) {
                best = temperature;
            }
        }
        return best;
    }
}
