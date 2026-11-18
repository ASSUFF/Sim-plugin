import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;

/**
 * Builds a cube whose edge length is the global parameter L.
 * Prints L back out. Does not solve a physics study.
 */
public class ParameterBlock {
    public static void main(String[] args) {
        ModelUtil.initStandalone(false);
        try {
            Model model = ModelUtil.create("ParameterBlock");
            model.param().set("L", "20[mm]");
            model.component().create("comp1", true);
            model.component("comp1").geom().create("geom1", 3);
            model.component("comp1").geom("geom1").create("blk1", "Block");
            model.component("comp1").geom("geom1").feature("blk1").set("size", new String[] {"L", "L", "L"});
            model.component("comp1").geom("geom1").run();
            System.out.println("===RESULT===");
            System.out.println("L=" + model.param().get("L"));
            model.save("ParameterBlock.mph");
        } catch (Exception e) {
            System.err.println("FATAL: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        } finally {
            ModelUtil.disconnect();
        }
    }
}
