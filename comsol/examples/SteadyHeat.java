import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;
import java.util.Locale;

/**
 * Steady heat conduction across a square plate.
 * Left edge T_cold, right edge T_hot, other edges insulated.
 * With constant conductivity the area average is (T_cold + T_hot) / 2.
 */
public class SteadyHeat {
    public static void main(String[] args) {
        ModelUtil.initStandalone(false);
        try {
            Model model = ModelUtil.create("SteadyHeat");
            model.param().set("L", "0.1[m]");
            model.param().set("k", "10[W/(m*K)]");
            model.param().set("rho", "1000[kg/m^3]");
            model.param().set("Cp", "1000[J/(kg*K)]");
            model.param().set("T_cold", "300[K]");
            model.param().set("T_hot", "400[K]");

            model.component().create("comp1", true);
            model.component("comp1").geom().create("geom1", 2);
            model.component("comp1").geom("geom1").create("r1", "Rectangle");
            model.component("comp1").geom("geom1").feature("r1").set("size", new String[] {"L", "L"});
            model.component("comp1").geom("geom1").run();

            model.component("comp1").material().create("mat1", "Common");
            model.component("comp1").material("mat1").selection().all();
            model.component("comp1").material("mat1").propertyGroup("def")
                    .set("thermalconductivity", new String[] {"k", "0", "0", "0", "k", "0", "0", "0", "k"});
            model.component("comp1").material("mat1").propertyGroup("def").set("density", "rho");
            model.component("comp1").material("mat1").propertyGroup("def").set("heatcapacity", "Cp");

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

            model.component("comp1").physics().create("ht", "HeatTransfer", "geom1");
            model.component("comp1").physics("ht").create("tempCold", "TemperatureBoundary", 1);
            model.component("comp1").physics("ht").feature("tempCold").selection().named("selLeft");
            model.component("comp1").physics("ht").feature("tempCold").set("T0", "T_cold");
            model.component("comp1").physics("ht").create("tempHot", "TemperatureBoundary", 1);
            model.component("comp1").physics("ht").feature("tempHot").selection().named("selRight");
            model.component("comp1").physics("ht").feature("tempHot").set("T0", "T_hot");

            model.component("comp1").mesh().create("mesh1", "geom1");
            model.component("comp1").mesh("mesh1").feature("size").set("hauto", 5);
            model.component("comp1").mesh("mesh1").run();

            model.study().create("std1");
            model.study("std1").create("stat", "Stationary");
            model.study("std1").run();

            double tAvg = evaluate(model, "tavg", "AvSurface");
            double tMax = evaluate(model, "tmax", "MaxSurface");
            double tMin = evaluate(model, "tmin", "MinSurface");
            System.out.println("===RESULT===");
            System.out.printf(Locale.US, "T_avg_K=%.6f%n", tAvg);
            System.out.printf(Locale.US, "T_max_K=%.6f%n", tMax);
            System.out.printf(Locale.US, "T_min_K=%.6f%n", tMin);
            model.save("SteadyHeat.mph");
        } catch (Exception e) {
            System.err.println("FATAL: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        } finally {
            ModelUtil.disconnect();
        }
    }

    private static double evaluate(Model model, String tag, String type) {
        model.result().numerical().create(tag, type);
        model.result().numerical(tag).selection().all();
        model.result().numerical(tag).set("expr", new String[] {"T"});
        double[][] data = model.result().numerical(tag).getReal();
        if (data.length == 0 || data[0].length == 0) {
            throw new IllegalStateException("empty " + type);
        }
        return data[0][0];
    }
}
